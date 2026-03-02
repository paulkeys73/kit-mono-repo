# app/services/image/run.py

from app.services.image.image_generator import generate_images_for_post

def main():
    mock_post = {
        "title": "Test Blog Post",
        "slug": "test-blog-post",
        "sections": {
            "Introduction": {},
            "Main Topic": {},
            "Conclusion": {}
        }
    }

    images = generate_images_for_post(mock_post)
    for img in images:
        print(f"Generated: {img}")

if __name__ == "__main__":
    main()
