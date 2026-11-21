using System.Collections.Concurrent;
using System.Diagnostics;
using System.Text;
using System.Text.Json;
using LMS.Data;
using LMS.Models;

namespace LMS.Services
{
    public class JobState
    {
        public string Status { get; set; } = "Running";   // Running | Done | Failed
        public string Message { get; set; } = "Queued...";
        public int? VideoId { get; set; }
        public string? Error { get; set; }
    }

    public class ProcessingService
    {
        // Python scripts share files in /AI, so only one lecture runs at a time.
        private static readonly SemaphoreSlim PipelineLock = new(1, 1);

        private readonly ConcurrentDictionary<string, JobState> _jobs = new();
        private readonly ConcurrentDictionary<string, string> _activeByHash = new();
        private readonly IServiceScopeFactory _scopeFactory;
        private readonly IWebHostEnvironment _env;
        private readonly string _pythonPath;

        public ProcessingService(
            IServiceScopeFactory scopeFactory,
            IWebHostEnvironment env,
            IConfiguration config)
        {
            _scopeFactory = scopeFactory;
            _env = env;
            _pythonPath = config["Python:Path"] ?? "python";
        }

        private string AiFolder => Path.Combine(_env.ContentRootPath, "AI");
        private string UploadFolder => Path.Combine(_env.WebRootPath, "uploads");

        public JobState? Get(string jobId) =>
            _jobs.TryGetValue(jobId, out var job) ? job : null;

        public string StartJob(string videoHash, string? savedPath, string? videoUrl, string uploadTitle)
        {
            // Same lecture already being processed? Reuse that job instead of starting another.
            if (_activeByHash.TryGetValue(videoHash, out var activeId)
                && _jobs.TryGetValue(activeId, out var activeJob)
                && activeJob.Status == "Running")
            {
                return activeId;
            }

            string jobId = Guid.NewGuid().ToString("N");
            var job = new JobState();
            _jobs[jobId] = job;
            _activeByHash[videoHash] = jobId;

            _ = Task.Run(() => RunJobAsync(job, videoHash, savedPath, videoUrl, uploadTitle));

            return jobId;
        }

        private async Task RunJobAsync(
            JobState job, string videoHash, string? savedPath, string? videoUrl, string uploadTitle)
        {
            try
            {
                job.Message = "Waiting for another lecture to finish...";
                await PipelineLock.WaitAsync();
                try
                {
                    await RunPipelineAsync(job, videoHash, savedPath, videoUrl, uploadTitle);
                }
                finally
                {
                    PipelineLock.Release();
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine(ex);
                job.Status = "Failed";
                job.Error = ex.Message;
            }
            finally
            {
                _activeByHash.TryRemove(videoHash, out _);
            }
        }

        private async Task RunPipelineAsync(
            JobState job, string videoHash, string? savedPath, string? videoUrl, string uploadTitle)
        {
            Directory.CreateDirectory(UploadFolder);

            foreach (var name in new[]
            {
                "transcript.txt", "summary.txt", "title.txt",
                "summary.json", "notes.json", "quiz.json", "final_output.json"
            })
            {
                try { File.Delete(Path.Combine(AiFolder, name)); } catch { }
            }

            string audioPath;
            string title = uploadTitle;

            if (savedPath != null)
            {
                audioPath = savedPath;
            }
            else
            {
                job.Message = "Downloading audio from YouTube...";

                foreach (var f in Directory.GetFiles(UploadFolder, "*.mp3"))
                {
                    try { File.Delete(f); } catch { }
                }

                await RunPythonAsync("download_audio.py", $"\"{videoUrl}\" \"{UploadFolder}\"");

                audioPath = Directory.GetFiles(UploadFolder, "*.mp3")
                    .OrderByDescending(File.GetCreationTime)
                    .FirstOrDefault()
                    ?? throw new Exception("MP3 download failed.");

                string titlePath = Path.Combine(AiFolder, "title.txt");
                title = File.Exists(titlePath)
                    ? (await File.ReadAllTextAsync(titlePath)).Trim()
                    : "Untitled Lecture";
            }

            job.Message = "Transcribing speech (this can take a few minutes)...";
            await RunPythonAsync("transcribe.py", $"\"{audioPath}\"");

            string transcriptPath = Path.Combine(AiFolder, "transcript.txt");
            if (!File.Exists(transcriptPath))
                throw new Exception("Transcript file was not generated.");
            string transcript = await File.ReadAllTextAsync(transcriptPath);

            job.Message = "Starting AI model...";
            await EnsureOllamaRunningAsync();

            job.Message = "Generating summary...";
            await RunPythonAsync("summary.py");

            job.Message = "Generating notes...";
            await RunPythonAsync("notes.py");

            job.Message = "Generating quiz...";
            await RunPythonAsync("quiz.py");

            job.Message = "Combining results...";
            await RunPythonAsync("combine_results.py");

            string finalPath = Path.Combine(AiFolder, "final_output.json");
            if (!File.Exists(finalPath))
                throw new Exception("final_output.json was not generated.");

            AIResponse ai = JsonSerializer.Deserialize<AIResponse>(
                await File.ReadAllTextAsync(finalPath))
                ?? throw new Exception("Failed to parse AI response.");

            foreach (var q in ai.Quiz)
            {
                if (q.Options == null || q.Options.Count != 4)
                    throw new Exception($"Question '{q.Question}' does not have 4 options.");
                if (string.IsNullOrWhiteSpace(q.Question) || string.IsNullOrWhiteSpace(q.Answer))
                    throw new Exception("Quiz contains an empty question or answer.");
                if (!q.Options.Contains(q.Answer))
                    throw new Exception($"Answer for '{q.Question}' does not match any option.");
            }

            job.Message = "Saving results...";

            var video = new Video
            {
                Title = title,
                VideoHash = videoHash,
                VideoPath = savedPath,
                VideoUrl = videoUrl,
                SourceType = savedPath != null ? "Upload" : "Link",
                Transcript = transcript,
                Summary = ai.Summary,
                Notes = JsonSerializer.Serialize(ai.Notes),
                Quiz = ""
            };

            var questions = ai.Quiz.Select(q => new QuizQuestion
            {
                Video = video,
                Question = q.Question,
                OptionA = q.Options[0],
                OptionB = q.Options[1],
                OptionC = q.Options[2],
                OptionD = q.Options[3],
                CorrectAnswer = q.Answer
            }).ToList();

            using (var scope = _scopeFactory.CreateScope())
            {
                var db = scope.ServiceProvider.GetRequiredService<ApplicationDbContext>();
                db.Videos.Add(video);
                db.QuizQuestions.AddRange(questions);
                await db.SaveChangesAsync();
            }

            job.VideoId = video.Id;
            job.Message = "Done!";
            job.Status = "Done";
        }

        // ------------------------------------------------------------
        // Python
        // ------------------------------------------------------------
        private async Task RunPythonAsync(string scriptName, string arguments = "")
        {
            var psi = new ProcessStartInfo
            {
                FileName = _pythonPath,
                Arguments = $"{scriptName} {arguments}",
                WorkingDirectory = AiFolder,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
                CreateNoWindow = true,
                StandardOutputEncoding = Encoding.UTF8,
                StandardErrorEncoding = Encoding.UTF8
            };
            psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";

            var started = DateTime.Now;
            Console.WriteLine($"[{started:HH:mm:ss}] START {scriptName}");

            using var process = Process.Start(psi)
                ?? throw new InvalidOperationException("Failed to start python process.");

            Task<string> stdoutTask = process.StandardOutput.ReadToEndAsync();
            Task<string> stderrTask = process.StandardError.ReadToEndAsync();
            await process.WaitForExitAsync();

            string output = await stdoutTask;
            string error = await stderrTask;

            Console.WriteLine(
                $"[{DateTime.Now:HH:mm:ss}] END {scriptName} " +
                $"({(DateTime.Now - started).TotalSeconds:F1}s) Exit={process.ExitCode}");
            Console.WriteLine("STDOUT:\n" + output);
            Console.WriteLine("STDERR:\n" + error);

            if (process.ExitCode != 0)
            {
                string tail = error.Length > 600 ? error[^600..] : error;
                throw new Exception($"{scriptName} failed (exit {process.ExitCode}): {tail}");
            }
        }

        // ------------------------------------------------------------
        // Ollama
        // ------------------------------------------------------------
        private static async Task<bool> IsOllamaRunningAsync()
        {
            try
            {
                using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(5) };
                using var response = await client.GetAsync("http://127.0.0.1:11434/api/tags");
                return response.IsSuccessStatusCode;
            }
            catch
            {
                return false;
            }
        }

        private static async Task EnsureOllamaRunningAsync()
        {
            if (await IsOllamaRunningAsync()) return;

            string localPath = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Programs", "Ollama", "ollama.exe");

            var psi = new ProcessStartInfo
            {
                FileName = File.Exists(localPath) ? localPath : "ollama", // falls back to PATH
                Arguments = "serve",
                UseShellExecute = false,
                CreateNoWindow = true
                // Output is NOT redirected: an unread pipe would eventually block Ollama.
            };

            try
            {
                Process.Start(psi);
            }
            catch (Exception ex)
            {
                throw new Exception("Could not start Ollama. Is it installed?", ex);
            }

            for (int i = 0; i < 30; i++)
            {
                await Task.Delay(1000);
                if (await IsOllamaRunningAsync()) return;
            }

            throw new Exception("Ollama did not start within 30 seconds.");
        }
    }
}