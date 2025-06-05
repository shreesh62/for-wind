import webbrowser

def open_website(command):
    command = command.lower()
    print(f"Received command in open_website: {command}")  # Debug print

    common_sites = {
        "youtube": "https://www.youtube.com",
        "google": "https://www.google.com",
        "instagram": "https://www.instagram.com",
        "facebook": "https://www.facebook.com",
        "twitter": "https://www.twitter.com",
        "reddit": "https://www.reddit.com",
        "github": "https://www.github.com",
        "spotify": "https://www.spotify.com"
    }

    for site in common_sites:
        if site in command:
            print(f"Matched site: {site}")  # Debug print
            webbrowser.open(common_sites[site])
            return f"Opening {site}"

    words = command.split()
    for word in words:
        if "." in word:
            url = word
            if not url.startswith("http"):
                url = "https://" + url
            print(f"Opening URL-like word: {url}")  # Debug print
            webbrowser.open(url)
            return f"Opening {url}"

    last_word = command.split()[-1]
    url = f"https://www.{last_word}.com"
    try:
        print(f"Trying last word as website: {url}")  # Debug print
        webbrowser.open(url)
        return f"Opening {url}"
    except Exception as e:
        print(f"Exception opening URL: {e}")  # Debug print
        return "Sorry, I can't open that site."

    return "Sorry, I don't know how to open that."
import webbrowser
import urllib.parse

def play_youtube_song(command):
    command = command.lower()
    if "play" in command:
        song = command.replace("play", "").strip()
        query = urllib.parse.quote(song)
        url = f"https://www.youtube.com/results?search_query={query}"
        webbrowser.open(url)
        return f"Playing {song} on YouTube"
    return "I didn't catch the song name."