using Microsoft.AspNetCore.Http;
using System.ComponentModel.DataAnnotations;

namespace LMS.ViewModels
{
    public class VideoInputViewModel
    {
        [Display(Name = "Upload Video")]
        public IFormFile? VideoFile { get; set; }

        [Display(Name = "Video Link")]
        public string? VideoUrl { get; set; }
    }
}