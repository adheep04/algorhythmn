"""
Popular artists list for the Algorhythmn recommendation system.
This module contains a curated list of popular artists that users can rate.
"""

# Popular artists set - can be easily modified to add/remove artists
ARTISTS = {
    "Frank Ocean",
    "Phoebe Bridgers", 
    "Taylor Swift",
    "Billie Eilish",
    "The Weeknd",
    "Ariana Grande",
    "Drake",
    "Olivia Rodrigo",
    "Harry Styles",
    "Dua Lipa",
    "Post Malone",
    "Ed Sheeran",
    "Adele",
    "Bruno Mars",
    "Justin Bieber",
    "Rihanna",
    "Beyoncé",
    "Kanye West",
    "Kendrick Lamar",
    "Travis Scott"
}

def get_artists_list():
    """
    Return the artists as a list for API consumption.
    
    Returns:
        list: List of artist names
    """
    return list(ARTISTS)

def get_artists_count():
    """
    Return the number of artists in the list.
    
    Returns:
        int: Number of artists
    """
    return len(ARTISTS)

def add_artist(artist_name):
    """
    Add a new artist to the list.
    
    Args:
        artist_name (str): Name of the artist to add
    """
    ARTISTS.add(artist_name)

def remove_artist(artist_name):
    """
    Remove an artist from the list.
    
    Args:
        artist_name (str): Name of the artist to remove
    """
    ARTISTS.discard(artist_name)
