using QuestPDF.Fluent;
using QuestPDF.Helpers;
using QuestPDF.Infrastructure;

namespace LMS.Services
{
    public class PdfService
    {
        public byte[] GeneratePdf(string title, string summary, string notes, string quiz)
        {
            QuestPDF.Settings.License = LicenseType.Community;

            return Document.Create(container =>
            {
                container.Page(page =>
                {
                    page.Margin(30);

                    page.Header()
                        .Text("AI Generated Learning Content")
                        .FontSize(24)
                        .Bold();

                    page.Content().Column(col =>
                    {
                        col.Spacing(20);

                        col.Item().Text($"Video Title: {title}")
                            .FontSize(18)
                            .Bold();

                        col.Item().Text("SUMMARY")
                            .FontSize(18)
                            .Bold();

                        col.Item().Text(summary);

                        col.Item().Text("DETAILED STUDY NOTES")
                            .FontSize(18)
                            .Bold();

                        col.Item().Text(notes);

                        col.Item().Text("QUIZ")
                            .FontSize(18)
                            .Bold();

                        col.Item().Text(quiz);
                    });

                    page.Footer()
                        .AlignCenter()
                        .Text($"Generated on {DateTime.Now}");
                });
            }).GeneratePdf();
        }
    }
}