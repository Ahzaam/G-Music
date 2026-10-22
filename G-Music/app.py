import os
import tempfile
import re
import random
import hashlib
from flask import Flask, render_template, jsonify, request, send_file
from flask_cors import CORS
from mutagen import File
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.mp4 import MP4
from mutagen.oggvorbis import OggVorbis
import mimetypes
import threading
import time

app = Flask(__name__)
app.secret_key = 'g-music-session-key-change-in-prod'
CORS(app)


# ========== LINKED LIST ADT ==========
class SongNode:
    def __init__(self, song_data):
        self.song = song_data
        self.next = None
        self.prev = None


class PlaylistADT:
    """Doubly Linked List for playlist management"""
    def __init__(self, name="My Playlist"):
        self.name = name
        self.head = None
        self.tail = None
        self.size = 0
        self.current = None

    def add_song(self, song_data):
        if self.song_exists(song_data.get('path')):
            return False
        new_node = SongNode(song_data)
        if self.head is None:
            self.head = self.tail = new_node
        else:
            self.tail.next = new_node
            new_node.prev = self.tail
            self.tail = new_node
        self.size += 1
        return True

    def add_song_at_position(self, song_data, position):
        if self.song_exists(song_data.get('path')):
            return False
        if position < 1 or position > self.size + 1:
            return False
        new_node = SongNode(song_data)
        if position == 1:
            new_node.next = self.head
            if self.head:
                self.head.prev = new_node
            self.head = new_node
            if self.tail is None:
                self.tail = new_node
        elif position == self.size + 1:
            new_node.prev = self.tail
            if self.tail:
                self.tail.next = new_node
            self.tail = new_node
            if self.head is None:
                self.head = new_node
        else:
            current = self.head
            for _ in range(1, position - 1):
                current = current.next
            new_node.next = current.next
            new_node.prev = current
            if current.next:
                current.next.prev = new_node
            current.next = new_node
        self.size += 1
        return True

    def song_exists(self, song_path):
        current = self.head
        while current:
            if current.song.get('path') == song_path:
                return True
            current = current.next
        return False

    def remove_song(self, position):
        if position < 1 or position > self.size or self.head is None:
            return None
        removed_node = None
        if position == 1:
            removed_node = self.head
            self.head = self.head.next
            if self.head:
                self.head.prev = None
            else:
                self.tail = None
        elif position == self.size:
            removed_node = self.tail
            self.tail = self.tail.prev
            if self.tail:
                self.tail.next = None
            else:
                self.head = None
        else:
            current = self.head
            for _ in range(1, position):
                current = current.next
            removed_node = current
            current.prev.next = current.next
            current.next.prev = current.prev
        self.size -= 1
        if self.current == removed_node:
            self.current = self.head
        return removed_node.song

    def move_song(self, from_position, to_position):
        if not (1 <= from_position <= self.size and 1 <= to_position <= self.size):
            return False
        if from_position == to_position:
            return True
        removed_song = self.remove_song(from_position)
        return self.add_song_at_position(removed_song, to_position)

    def get_all_songs(self):
        songs, current = [], self.head
        while current:
            songs.append(current.song)
            current = current.next
        return songs

    def play_shuffled(self):
        songs = self.get_all_songs()
        random.shuffle(songs)
        return songs

    def clear(self):
        self.head = self.tail = self.current = None
        self.size = 0


# ========== MUSIC PLAYER ==========
class MusicPlayer:
    def __init__(self):
        self.reset_all_data()

    def reset_all_data(self):
        self.current_folder = None
        self.library = []
        self.current_index = 0
        self.temp_files = {}
        self.upload_dir = None
        self.cleanup_thread = None
        self.playlists = {}
        self.current_playlist_id = None
        self.favorites = PlaylistADT("Favorites")
        self.playback_mode = "sequential"
        self.current_playing_playlist_id = None
        self.current_playlist_song_index = 0
        self.create_playlist("My Playlist")
        return True

    def get_upload_dir(self):
        if self.upload_dir is None:
            self.upload_dir = os.path.join(tempfile.gettempdir(), 'gmusic_uploads')
            os.makedirs(self.upload_dir, exist_ok=True)
        return self.upload_dir

    def cleanup_old_files(self):
        while True:
            time.sleep(3600)
            try:
                now = time.time()
                for filename, filepath in list(self.temp_files.items()):
                    if os.path.exists(filepath) and (now - os.path.getctime(filepath)) > 3600:
                        try:
                            os.remove(filepath)
                            del self.temp_files[filename]
                        except Exception:
                            pass
            except Exception:
                pass

    def parse_filename(self, filename):
        name = os.path.splitext(filename)[0]
        name = re.sub(r'\[.*?\]|\(.*?\)|\{.*?\}', '', name)
        name = re.sub(r'^\d+\s*[-._]?\s*', '', name)
        artist, title = 'Unknown Artist', name.strip()
        for sep in [' - ', ' _ ', ' – ', ' — ', ' | ']:
            if sep in name:
                parts = name.split(sep, 1)
                if len(parts) == 2:
                    artist, title = parts[0].strip(), parts[1].strip()
                    break
        if artist == 'Unknown Artist' and '-' in title:
            parts = title.rsplit('-', 1)
            if len(parts) == 2:
                artist, title = parts[0].strip(), parts[1].strip()
        artist, title = self.clean_name(artist), self.clean_name(title)
        if len(artist) > 50:
            artist = 'Unknown Artist'
        return artist, title

    def clean_name(self, name):
        name = name.replace('_', ' ').replace('-', ' ')
        name = ' '.join(name.split())
        return ' '.join(w if (w.isupper() and len(w) > 1) else w.capitalize() for w in name.split())

    # ========== FILE HASH FOR DUPLICATE DETECTION ==========
    def compute_file_hash(self, file_path, chunk_size=65536):
        """Compute MD5 hash of file contents for reliable duplicate detection."""
        md5 = hashlib.md5()
        try:
            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    md5.update(chunk)
            return md5.hexdigest()
        except Exception as e:
            print(f"Hash error {file_path}: {e}")
            return None

    def process_uploaded_files(self, files, folder_name):
        music_files = []
        skipped = []          # [{name, reason}] for detailed feedback
        upload_dir = self.get_upload_dir()

        if self.cleanup_thread is None or not self.cleanup_thread.is_alive():
            self.cleanup_thread = threading.Thread(target=self.cleanup_old_files, daemon=True)
            self.cleanup_thread.start()

        # Build fast lookup sets from current library
        existing_hashes = {s.get('hash') for s in self.library if s.get('hash')}
        existing_filenames = {s.get('filename') for s in self.library if s.get('filename')}
        existing_paths = {s.get('path') for s in self.library if s.get('path')}

        for file in files:
            temp_path = None
            try:
                filename = file.filename
                safe_filename = re.sub(r'[<>:"/\\|?*]', '_', os.path.basename(filename))

                # Save to unique temp path
                temp_path = os.path.join(upload_dir, safe_filename)
                counter = 1
                while os.path.exists(temp_path):
                    name, ext = os.path.splitext(safe_filename)
                    temp_path = os.path.join(upload_dir, f"{name}_{counter}{ext}")
                    counter += 1

                file.save(temp_path)
                actual_filename = os.path.basename(temp_path)

                # ---- DUPLICATE CHECK 1: file path (unlikely but possible) ----
                if temp_path in existing_paths:
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
                    skipped.append({
                        'name': filename,
                        'reason': 'Already in library'
                    })
                    continue

                # ---- DUPLICATE CHECK 2: content hash (catches same file, diff name) ----
                file_hash = self.compute_file_hash(temp_path)
                if file_hash and file_hash in existing_hashes:
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
                    skipped.append({
                        'name': filename,
                        'reason': 'Identical file already in library'
                    })
                    continue

                # ---- DUPLICATE CHECK 3: filename collision (same name, diff content) ----
                # Only skip if the song's original uploaded name matches an existing one
                original_name_dup = any(
                    os.path.basename(s.get('path', '')).startswith(safe_filename.rsplit('.', 1)[0])
                    and s.get('filename') == safe_filename
                    for s in self.library
                )
                if original_name_dup:
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
                    skipped.append({
                        'name': filename,
                        'reason': 'Same filename already in library'
                    })
                    continue

                # Register temp file
                self.temp_files[actual_filename] = temp_path

                # Metadata
                metadata = self.get_metadata(temp_path)
                if not metadata.get('title'):
                    artist, title = self.parse_filename(safe_filename)
                    metadata['artist'], metadata['title'] = artist, title

                song_data = {
                    'path': temp_path,
                    'filename': actual_filename,
                    'title': metadata.get('title') or 'Unknown Title',
                    'artist': metadata.get('artist') or 'Unknown Artist',
                    'album': metadata.get('album') or 'Unknown Album',
                    'duration': metadata.get('duration', 0),
                    'hash': file_hash,
                    'id': str(int(time.time() * 1000)) + str(counter)
                }

                music_files.append(song_data)

                # Update local lookup sets so batch uploads don't self-duplicate
                if file_hash:
                    existing_hashes.add(file_hash)
                existing_filenames.add(actual_filename)
                existing_paths.add(temp_path)

            except Exception as e:
                print(f"Error processing {file.filename}: {e}")
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
                skipped.append({
                    'name': file.filename,
                    'reason': f'Processing error'
                })
                continue

        if music_files:
            self.library.extend(music_files)
            self.current_folder = folder_name
            for playlist in self.playlists.values():
                if playlist.name == "My Playlist":
                    for song in music_files:
                        playlist.add_song(song)
                    break

        return {
            'success': True,
            'files': music_files,
            'count': len(music_files),
            'total_library_size': len(self.library),
            'skipped': skipped,
            'skipped_duplicates': len(skipped)
        }

    def get_metadata(self, file_path):
        metadata = {'title': None, 'artist': None, 'album': None, 'duration': 0}
        try:
            audio = File(file_path)
            if audio:
                if hasattr(audio.info, 'length'):
                    metadata['duration'] = int(audio.info.length)
                if hasattr(audio, 'get'):
                    if audio.get('TIT2'):
                        metadata['title'] = str(audio['TIT2'])
                    elif audio.get('title'):
                        v = audio['title']
                        metadata['title'] = v[0] if isinstance(v, list) else str(v)
                    if audio.get('TPE1'):
                        metadata['artist'] = str(audio['TPE1'])
                    elif audio.get('artist'):
                        v = audio['artist']
                        metadata['artist'] = v[0] if isinstance(v, list) else str(v)
                    if audio.get('TALB'):
                        metadata['album'] = str(audio['TALB'])
                    elif audio.get('album'):
                        v = audio['album']
                        metadata['album'] = v[0] if isinstance(v, list) else str(v)

                if isinstance(audio, MP3):
                    if audio.get('TIT2'): metadata['title'] = str(audio['TIT2'])
                    if audio.get('TPE1'): metadata['artist'] = str(audio['TPE1'])
                    if audio.get('TALB'): metadata['album'] = str(audio['TALB'])
                elif isinstance(audio, FLAC):
                    if audio.get('title'): metadata['title'] = audio['title'][0]
                    if audio.get('artist'): metadata['artist'] = audio['artist'][0]
                    if audio.get('album'): metadata['album'] = audio['album'][0]
                elif isinstance(audio, MP4):
                    if '\xa9nam' in audio: metadata['title'] = audio['\xa9nam'][0]
                    if '\xa9ART' in audio: metadata['artist'] = audio['\xa9ART'][0]
                    if '\xa9alb' in audio: metadata['album'] = audio['\xa9alb'][0]
                elif isinstance(audio, OggVorbis):
                    if 'title' in audio: metadata['title'] = audio['title'][0]
                    if 'artist' in audio: metadata['artist'] = audio['artist'][0]
                    if 'album' in audio: metadata['album'] = audio['album'][0]
        except Exception as e:
            print(f"Metadata error {file_path}: {e}")

        for key in ['title', 'artist', 'album']:
            if metadata[key] and isinstance(metadata[key], list):
                metadata[key] = metadata[key][0]
            if metadata[key]:
                metadata[key] = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', str(metadata[key])).strip()
        return metadata

    # ========== PLAYLIST MGMT ==========
    def create_playlist(self, name):
        playlist_id = str(int(time.time() * 1000))
        self.playlists[playlist_id] = PlaylistADT(name)
        return {'id': playlist_id, 'name': name, 'size': 0}

    def delete_playlist(self, playlist_id):
        if playlist_id in self.playlists:
            del self.playlists[playlist_id]
            if self.current_playlist_id == playlist_id:
                self.current_playlist_id = None
            if self.current_playing_playlist_id == playlist_id:
                self.current_playing_playlist_id = None
                self.current_playlist_song_index = 0
            return True
        return False

    def get_all_playlists(self):
        return [
            {'id': pid, 'name': pl.name, 'size': pl.size, 'songs': pl.get_all_songs()}
            for pid, pl in self.playlists.items()
        ]

    def add_to_playlist(self, playlist_id, song_data, position=None):
        if playlist_id not in self.playlists:
            return False
        pl = self.playlists[playlist_id]
        if pl.song_exists(song_data.get('path')):
            return False
        return pl.add_song_at_position(song_data, position) if position else pl.add_song(song_data)

    def remove_from_playlist(self, playlist_id, position):
        if playlist_id not in self.playlists:
            return None
        return self.playlists[playlist_id].remove_song(position)

    def move_in_playlist(self, playlist_id, from_pos, to_pos):
        if playlist_id not in self.playlists:
            return False
        return self.playlists[playlist_id].move_song(from_pos, to_pos)

    def get_playlist_songs(self, playlist_id):
        if playlist_id not in self.playlists:
            return []
        pl = self.playlists[playlist_id]
        return pl.play_shuffled() if self.playback_mode == "shuffled" else pl.get_all_songs()

    def set_playback_mode(self, mode):
        if mode in ["sequential", "shuffled"]:
            self.playback_mode = mode
            return True
        return False

    def add_to_favorites(self, song_data):
        if self.favorites.song_exists(song_data.get('path')):
            return False
        return self.favorites.add_song(song_data)

    def remove_from_favorites(self, position):
        return self.favorites.remove_song(position)

    def get_favorites(self):
        return self.favorites.get_all_songs()

    # ========== PLAYLIST PLAYBACK ==========
    def set_current_playing_playlist(self, playlist_id):
        if playlist_id in self.playlists:
            self.current_playing_playlist_id = playlist_id
            self.current_playlist_song_index = 0
            return True
        return False

    def get_current_playlist_song(self):
        if self.current_playing_playlist_id in self.playlists:
            songs = self.playlists[self.current_playing_playlist_id].get_all_songs()
            if 0 <= self.current_playlist_song_index < len(songs):
                return songs[self.current_playlist_song_index]
        return None

    def play_next_in_playlist(self):
        if self.current_playing_playlist_id in self.playlists:
            songs = self.playlists[self.current_playing_playlist_id].get_all_songs()
            if songs:
                self.current_playlist_song_index = (self.current_playlist_song_index + 1) % len(songs)
                return songs[self.current_playlist_song_index]
        return None

    def play_previous_in_playlist(self):
        if self.current_playing_playlist_id in self.playlists:
            songs = self.playlists[self.current_playing_playlist_id].get_all_songs()
            if songs:
                self.current_playlist_song_index = (self.current_playlist_song_index - 1 + len(songs)) % len(songs)
                return songs[self.current_playlist_song_index]
        return None

    def play_song_from_playlist(self, playlist_id, position):
        if playlist_id in self.playlists:
            songs = self.playlists[playlist_id].get_all_songs()
            if 1 <= position <= len(songs):
                self.current_playing_playlist_id = playlist_id
                self.current_playlist_song_index = position - 1
                return songs[position - 1]
        return None

    def get_current_playlist_info(self):
        if self.current_playing_playlist_id in self.playlists:
            pl = self.playlists[self.current_playing_playlist_id]
            return {
                'id': self.current_playing_playlist_id,
                'name': pl.name,
                'index': self.current_playlist_song_index,
                'size': pl.size
            }
        return None


music_player = MusicPlayer()


# ========== ROUTES ==========
@app.route('/')
def index():
    music_player.reset_all_data()
    return render_template('index.html')


@app.route('/api/reset', methods=['POST'])
def reset_all():
    music_player.reset_all_data()
    return jsonify({
        'success': True, 'message': 'All data reset',
        'library': music_player.library,
        'playlists': music_player.get_all_playlists(),
        'favorites': music_player.get_favorites()
    })


@app.route('/api/upload_files', methods=['POST'])
def upload_files():
    try:
        files = request.files.getlist('files[]')
        folder_name = request.form.get('folder_path', 'uploaded_files')
        if not files:
            return jsonify({'success': False, 'error': 'No files uploaded'})
        return jsonify(music_player.process_uploaded_files(files, folder_name))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/audio/<path:filepath>')
def serve_audio(filepath):
    try:
        import urllib.parse
        filepath = urllib.parse.unquote(filepath)
        filename = os.path.basename(filepath)
        if filename in music_player.temp_files:
            filepath = music_player.temp_files[filename]
        if not os.path.exists(filepath):
            return jsonify({'error': 'File not found'}), 404

        size = os.path.getsize(filepath)
        mime_type = mimetypes.guess_type(filepath)[0] or 'audio/mpeg'
        range_header = request.headers.get('Range')

        if not range_header:
            return send_file(filepath, mimetype=mime_type)

        range_match = range_header.strip().split('=')[1].split('-')
        byte1 = int(range_match[0]) if range_match[0] else 0
        byte2 = int(range_match[1]) if len(range_match) > 1 and range_match[1] else size - 1
        if byte1 >= size or byte2 >= size:
            return send_file(filepath, mimetype=mime_type)

        length = byte2 - byte1 + 1
        with open(filepath, 'rb') as f:
            f.seek(byte1)
            data = f.read(length)

        response = app.response_class(data, 206, mimetype=mime_type, direct_passthrough=True)
        response.headers.add('Content-Range', f'bytes {byte1}-{byte2}/{size}')
        response.headers.add('Accept-Ranges', 'bytes')
        response.headers.add('Content-Length', str(length))
        return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Playlists
@app.route('/api/playlists', methods=['GET'])
def get_playlists():
    return jsonify({'success': True, 'playlists': music_player.get_all_playlists()})


@app.route('/api/playlists', methods=['POST'])
def create_playlist():
    data = request.get_json()
    return jsonify({'success': True, 'playlist': music_player.create_playlist(data.get('name', 'New Playlist'))})


@app.route('/api/playlists/<playlist_id>', methods=['DELETE'])
def delete_playlist(playlist_id):
    return jsonify({'success': music_player.delete_playlist(playlist_id)})


@app.route('/api/playlists/<playlist_id>/songs', methods=['GET'])
def get_playlist_songs(playlist_id):
    return jsonify({
        'success': True,
        'songs': music_player.get_playlist_songs(playlist_id),
        'playback_mode': music_player.playback_mode
    })


@app.route('/api/playlists/<playlist_id>/songs', methods=['POST'])
def add_to_playlist(playlist_id):
    data = request.get_json()
    return jsonify({'success': music_player.add_to_playlist(playlist_id, data.get('song'), data.get('position'))})


@app.route('/api/playlists/<playlist_id>/songs/<int:position>', methods=['DELETE'])
def remove_from_playlist(playlist_id, position):
    removed = music_player.remove_from_playlist(playlist_id, position)
    return jsonify({'success': removed is not None, 'removed_song': removed})


@app.route('/api/playlists/<playlist_id>/move', methods=['POST'])
def move_in_playlist(playlist_id):
    data = request.get_json()
    return jsonify({'success': music_player.move_in_playlist(playlist_id, data.get('from_position'), data.get('to_position'))})


# Playlist playback
@app.route('/api/playlists/<playlist_id>/play', methods=['POST'])
def play_playlist(playlist_id):
    success = music_player.set_current_playing_playlist(playlist_id)
    return jsonify({'success': success, 'song': music_player.get_current_playlist_song(), 'playlist_id': playlist_id})


@app.route('/api/playlists/<playlist_id>/play/<int:position>', methods=['POST'])
def play_playlist_song(playlist_id, position):
    song = music_player.play_song_from_playlist(playlist_id, position)
    return jsonify({'success': song is not None, 'song': song, 'playlist_id': playlist_id, 'position': position})


@app.route('/api/playlists/next', methods=['GET'])
def play_next_in_playlist():
    song = music_player.play_next_in_playlist()
    return jsonify({'success': song is not None, 'song': song})


@app.route('/api/playlists/previous', methods=['GET'])
def play_previous_in_playlist():
    song = music_player.play_previous_in_playlist()
    return jsonify({'success': song is not None, 'song': song})


@app.route('/api/playlists/current', methods=['GET'])
def get_current_playlist():
    return jsonify({'success': True, 'playlist_info': music_player.get_current_playlist_info()})


@app.route('/api/playback/mode', methods=['POST'])
def set_playback_mode():
    data = request.get_json()
    success = music_player.set_playback_mode(data.get('mode', 'sequential'))
    return jsonify({'success': success, 'playback_mode': music_player.playback_mode})


# Favorites
@app.route('/api/favorites', methods=['GET'])
def get_favorites():
    return jsonify({'success': True, 'favorites': music_player.get_favorites()})


@app.route('/api/favorites', methods=['POST'])
def add_to_favorites():
    data = request.get_json()
    return jsonify({'success': music_player.add_to_favorites(data.get('song'))})


@app.route('/api/favorites/<int:position>', methods=['DELETE'])
def remove_from_favorites(position):
    removed = music_player.remove_from_favorites(position)
    return jsonify({'success': removed is not None, 'removed_song': removed})


# Library
@app.route('/api/library', methods=['GET'])
def get_library():
    return jsonify({'success': True, 'library': music_player.library})


@app.route('/api/sort_az', methods=['POST'])
def sort_az():
    music_player.library.sort(key=lambda x: x.get('title', '').lower())
    return jsonify({'success': True, 'library': music_player.library})


@app.route('/api/sort_za', methods=['POST'])
def sort_za():
    music_player.library.sort(key=lambda x: x.get('title', '').lower(), reverse=True)
    return jsonify({'success': True, 'library': music_player.library})


@app.route('/api/restore_order', methods=['POST'])
def restore_order():
    return jsonify({'success': True, 'library': music_player.library})


if __name__ == '__main__':
    app.run(debug=True, port=5000)