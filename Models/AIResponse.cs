using System.Text.Json.Serialization;

namespace LMS.Models
{
    public class AIResponse
    {
        [JsonPropertyName("summary")]
        public string Summary { get; set; } = "";

        [JsonPropertyName("notes")]
        public List<AINote> Notes { get; set; } = new();

        [JsonPropertyName("quiz")]
        public List<AIQuiz> Quiz { get; set; } = new();
    }

    public class AINote
    {
        [JsonPropertyName("title")]
        public string Title { get; set; } = "";

        [JsonPropertyName("content")]
        public List<AINoteSection> Content { get; set; } = new();
    }

    public class AINoteSection
    {
        [JsonPropertyName("heading")]
        public string Heading { get; set; } = "";

        [JsonPropertyName("text")]
        public string Text { get; set; } = "";
    }

    public class AIQuiz
    {
        [JsonPropertyName("question")]
        public string Question { get; set; } = "";

        [JsonPropertyName("options")]
        public List<string> Options { get; set; } = new();

        [JsonPropertyName("answer")]
        public string Answer { get; set; } = "";
    }
}