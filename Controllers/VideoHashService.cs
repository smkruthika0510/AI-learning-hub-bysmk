using System.Security.Cryptography;

namespace LMS.Services
{
    public class VideoHashService
    {
        // Generate SHA256 hash for uploaded files
        public async Task<string> GenerateFileHashAsync(IFormFile file)
        {
            using var sha = SHA256.Create();

            using var stream = file.OpenReadStream();

            byte[] hash = await sha.ComputeHashAsync(stream);

            return Convert.ToHexString(hash);
        }

        // Generate hash for video URLs
        public string GenerateUrlHash(string url)
        {
            using var sha = SHA256.Create();

            byte[] hash = sha.ComputeHash(
                System.Text.Encoding.UTF8.GetBytes(url.Trim().ToLower()));

            return Convert.ToHexString(hash);
        }
    }
}