using LMS.Models;

namespace LMS.ViewModels
{
    public class QuizResultViewModel
    {
        public int TotalQuestions { get; set; }

        public int CorrectAnswers { get; set; }

        public double Percentage { get; set; }

        public List<QuestionResult> Results { get; set; } = new();
    }

    public class QuestionResult
    {
        public string Question { get; set; } = "";

        public string SelectedAnswer { get; set; } = "";

        public string CorrectAnswer { get; set; } = "";

        public bool IsCorrect { get; set; }
    }
}