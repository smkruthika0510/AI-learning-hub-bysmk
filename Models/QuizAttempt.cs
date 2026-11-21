using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace LMS.Models
{
    public class QuizAttempt
    {
        [Key]
        public int Id { get; set; }

        public int VideoId { get; set; }

        public int QuizQuestionId { get; set; }

        public string SelectedAnswer { get; set; } = string.Empty;

        public string CorrectAnswer { get; set; } = string.Empty;

        public bool IsCorrect { get; set; }

        public DateTime SubmittedAt { get; set; } = DateTime.Now;
    }
}