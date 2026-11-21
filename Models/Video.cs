using System.ComponentModel.DataAnnotations;

namespace LMS.Models
{
    public class Video
    {
        [Key]
        public int Id { get; set; }

        [Required]
        public string VideoHash { get; set; } = string.Empty;

        public string? Title { get; set; }

        // Local uploaded file path
        public string? VideoPath { get; set; }

        // URL entered by the user
        public string? VideoUrl { get; set; }

        // Upload or Link
        public string? SourceType { get; set; }

        public string? Transcript { get; set; }

        public string? Summary { get; set; }

        public string? Quiz { get; set; }

        public string? Notes { get; set; }

        public DateTime CreatedAt { get; set; } = DateTime.Now;
    }
}