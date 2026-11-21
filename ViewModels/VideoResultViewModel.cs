using LMS.Models;

namespace LMS.ViewModels
{
    public class VideoResultViewModel
    {
        public int Id { get; set; }

        public string? Title { get; set; }

        public string? Summary { get; set; }

        public List<AINote> Notes { get; set; } = new();

        public bool IsFromDatabase { get; set; }

        // Interactive Quiz
        public List<QuizQuestion> QuizQuestions { get; set; } = new();
    }
}