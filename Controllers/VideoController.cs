using System.Text;
using System.Text.Json;
using LMS.Data;
using LMS.Models;
using LMS.Services;
using LMS.ViewModels;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace LMS.Controllers
{
    public class VideoController : Controller
    {
        private readonly IWebHostEnvironment _environment;
        private readonly VideoHashService _hashService;
        private readonly ApplicationDbContext _context;
        private readonly PdfService _pdfService;
        private readonly ProcessingService _processing;

        public VideoController(
            IWebHostEnvironment environment,
            VideoHashService hashService,
            ApplicationDbContext context,
            PdfService pdfService,
            ProcessingService processing)
        {
            _environment = environment;
            _hashService = hashService;
            _context = context;
            _pdfService = pdfService;
            _processing = processing;
        }

        // ---------------- helpers ----------------

        private List<AINote> DeserializeNotes(string? storedNotes)
        {
            if (string.IsNullOrWhiteSpace(storedNotes))
                return new List<AINote>();

            try
            {
                var notes = JsonSerializer.Deserialize<List<AINote>>(storedNotes);
                if (notes != null) return notes;
            }
            catch (JsonException)
            {
                // Old videos may contain plain text notes.
            }

            return new List<AINote>
            {
                new AINote
                {
                    Title = "Notes",
                    Content = storedNotes
                        .Split(Environment.NewLine, StringSplitOptions.RemoveEmptyEntries)
                        .Select(line => new AINoteSection { Heading = "", Text = line })
                        .ToList()
                }
            };
        }

        private List<QuizQuestion> DeduplicateQuizQuestions(List<QuizQuestion> questions) =>
            questions.GroupBy(q => q.Id).Select(g => g.First()).ToList();

        // ---------------- pages ----------------

        public IActionResult Index() => View(new VideoInputViewModel());

        [HttpPost]
        [RequestSizeLimit(2L * 1024 * 1024 * 1024)]
        [RequestFormLimits(MultipartBodyLengthLimit = 2L * 1024 * 1024 * 1024)]
        public async Task<IActionResult> ProcessVideo(VideoInputViewModel model)
        {
            if (model.VideoFile == null && string.IsNullOrWhiteSpace(model.VideoUrl))
            {
                ModelState.AddModelError("", "Please upload a video or enter a YouTube link.");
                return View("Index", model);
            }

            string videoHash = model.VideoFile != null
                ? await _hashService.GenerateFileHashAsync(model.VideoFile)
                : _hashService.GenerateUrlHash(model.VideoUrl!);

            // Already processed? Open it directly.
            var existing = await _context.Videos
                .AsNoTracking()
                .FirstOrDefaultAsync(v => v.VideoHash == videoHash);

            if (existing != null)
                return RedirectToAction(nameof(ViewVideo), new { id = existing.Id });

            string? savedPath = null;
            string title = "Untitled Lecture";

            if (model.VideoFile != null)
            {
                string uploadFolder = Path.Combine(_environment.WebRootPath, "uploads");
                Directory.CreateDirectory(uploadFolder);

                savedPath = Path.Combine(
                    uploadFolder,
                    Guid.NewGuid() + Path.GetExtension(model.VideoFile.FileName));

                using (var stream = new FileStream(savedPath, FileMode.Create))
                {
                    await model.VideoFile.CopyToAsync(stream);
                }

                title = Path.GetFileNameWithoutExtension(model.VideoFile.FileName);
            }

            string jobId = _processing.StartJob(
                videoHash,
                savedPath,
                model.VideoFile == null ? model.VideoUrl : null,
                title);

            return View("Processing", jobId);
        }

        [HttpGet]
        public IActionResult Status(string id)
        {
            var job = _processing.Get(id);

            if (job == null)
                return Json(new { status = "Failed", message = "", error = "Job not found (server restarted?).", videoId = (int?)null });

            return Json(new { status = job.Status, message = job.Message, error = job.Error, videoId = job.VideoId });
        }

        [HttpGet]
        public async Task<IActionResult> History()
        {
            var videos = await _context.Videos
                .OrderByDescending(v => v.CreatedAt)
                .ToListAsync();

            return View(videos);
        }

        [HttpGet]
        public async Task<IActionResult> ViewVideo(int id)
        {
            var video = await _context.Videos.FindAsync(id);
            if (video == null) return NotFound();

            var quizQuestions = DeduplicateQuizQuestions(
                await _context.QuizQuestions.Where(q => q.VideoId == video.Id).ToListAsync());

            return View("Result", new VideoResultViewModel
            {
                Id = video.Id,
                Title = video.Title,
                Summary = video.Summary,
                Notes = DeserializeNotes(video.Notes),
                IsFromDatabase = true,
                QuizQuestions = quizQuestions
            });
        }

        [HttpGet]
        public async Task<IActionResult> DownloadPdf(int id)
        {
            var video = await _context.Videos.FindAsync(id);
            if (video == null) return NotFound();

            var notesText = new StringBuilder();
            foreach (var note in DeserializeNotes(video.Notes))
            {
                notesText.AppendLine(note.Title);
                foreach (var section in note.Content)
                {
                    if (!string.IsNullOrWhiteSpace(section.Heading))
                        notesText.AppendLine(section.Heading);
                    notesText.AppendLine(section.Text);
                }
                notesText.AppendLine();
            }

            var questions = DeduplicateQuizQuestions(
                await _context.QuizQuestions.Where(q => q.VideoId == id).ToListAsync());

            var quizText = new StringBuilder();
            int n = 1;
            foreach (var q in questions)
            {
                quizText.AppendLine($"Q{n}. {q.Question}");
                quizText.AppendLine($"A) {q.OptionA}");
                quizText.AppendLine($"B) {q.OptionB}");
                quizText.AppendLine($"C) {q.OptionC}");
                quizText.AppendLine($"D) {q.OptionD}");
                quizText.AppendLine($"Answer: {q.CorrectAnswer}");
                quizText.AppendLine();
                n++;
            }

            var pdf = _pdfService.GeneratePdf(
                video.Title ?? "",
                video.Summary ?? "",
                notesText.ToString(),
                quizText.ToString());

            return File(pdf, "application/pdf", $"{video.Title}.pdf");
        }

        [HttpGet]
        public async Task<IActionResult> DeleteVideo(int id)
        {
            var video = await _context.Videos.FindAsync(id);
            if (video == null) return NotFound();

            _context.Videos.Remove(video);
            await _context.SaveChangesAsync();

            return RedirectToAction("History");
        }

        [HttpPost]
        public async Task<IActionResult> SubmitQuiz(int videoId)
        {
            var questions = DeduplicateQuizQuestions(
                await _context.QuizQuestions.Where(q => q.VideoId == videoId).ToListAsync());

            if (!questions.Any())
                return RedirectToAction("ViewVideo", new { id = videoId });

            var results = new List<QuestionResult>();
            int correct = 0;
            int position = 1;

            while (Request.Form.ContainsKey($"qid_{position}"))
            {
                string? qidRaw = Request.Form[$"qid_{position}"];
                string? selected = Request.Form[$"answer_{position}"];

                if (!int.TryParse(qidRaw, out int questionId))
                {
                    position++;
                    continue;
                }

                var question = questions.FirstOrDefault(q => q.Id == questionId);
                if (question == null)
                {
                    position++;
                    continue;
                }

                bool isCorrect = string.Equals(
                    selected?.Trim(),
                    question.CorrectAnswer?.Trim(),
                    StringComparison.OrdinalIgnoreCase);

                if (isCorrect) correct++;

                _context.QuizAttempts.Add(new QuizAttempt
                {
                    VideoId = videoId,
                    QuizQuestionId = question.Id,
                    SelectedAnswer = selected ?? "Not Answered",
                    CorrectAnswer = question.CorrectAnswer ?? string.Empty,
                    IsCorrect = isCorrect,
                    SubmittedAt = DateTime.Now
                });

                results.Add(new QuestionResult
                {
                    Question = question.Question,
                    SelectedAnswer = selected ?? "Not Answered",
                    CorrectAnswer = question.CorrectAnswer ?? string.Empty,
                    IsCorrect = isCorrect
                });

                position++;
            }

            await _context.SaveChangesAsync();

            return View("QuizResult", new QuizResultViewModel
            {
                TotalQuestions = results.Count,
                CorrectAnswers = correct,
                Percentage = results.Count > 0
                    ? Math.Round((double)correct * 100 / results.Count, 2)
                    : 0,
                Results = results
            });
        }
    }
}