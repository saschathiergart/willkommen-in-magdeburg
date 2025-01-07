from monitor_news import main
import os

def test_workflow():
    # Set required environment variables
    os.environ["GITHUB_REPOSITORY"] = "Packebusch/willkommen-in-magdeburg"
    # You'll need to create a GitHub token with repo access
    os.environ["GITHUB_TOKEN"] = "your-github-token"
    
    # Run the main workflow
    main()

if __name__ == "__main__":
    test_workflow() 