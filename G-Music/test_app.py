import pytest
import json
import os
import io
import tempfile
from app import app, PlaylistADT, MusicPlayer, SongNode, music_player


# ========== FIXTURES ==========

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture(autouse=True)
def reset_player_state():
    """Reset the global music_player before AND after each test."""
    music_player.reset_all_data()
    yield
    music_player.reset_all_data()


@pytest.fixture
def sample_song():
    return {
        'path': '/tmp/song1.mp3',
        'filename': 'song1.mp3',
        'title': 'Song One',
        'artist': 'Artist One',
        'album': 'Album One',
        'duration': 100,
        'hash': 'abc123hash',
        'id': '1'
    }


@pytest.fixture
def sample_song_2():
    return {
        'path': '/tmp/song2.mp3',
        'filename': 'song2.mp3',
        'title': 'Song Two',
        'artist': 'Artist Two',
        'album': 'Album Two',
        'duration': 200,
        'hash': 'def456hash',
        'id': '2'
    }


@pytest.fixture
def make_fake_upload():
    """Returns a helper that builds a Werkzeug FileStorage-like tuple for upload."""
    def _make(filename, content=b'fake audio data'):
        return (io.BytesIO(content), filename)
    return _make



# ============ ADT TESTS (PlaylistADT) =====================


class TestPlaylistADT:

    def test_new_playlist_is_empty(self):
        pl = PlaylistADT("Test")
        assert pl.name == "Test"
        assert pl.size == 0
        assert pl.head is None
        assert pl.tail is None

    def test_add_song(self, sample_song):
        pl = PlaylistADT()
        assert pl.add_song(sample_song) is True
        assert pl.size == 1
        assert pl.head.song['title'] == 'Song One'
        assert pl.tail.song['title'] == 'Song One'

    def test_add_multiple_songs(self, sample_song, sample_song_2):
        pl = PlaylistADT()
        pl.add_song(sample_song)
        pl.add_song(sample_song_2)
        assert pl.size == 2
        assert pl.head.song['path'] == sample_song['path']
        assert pl.tail.song['path'] == sample_song_2['path']

    def test_duplicate_song_rejected(self, sample_song):
        pl = PlaylistADT()
        pl.add_song(sample_song)
        assert pl.add_song(sample_song) is False
        assert pl.size == 1

    def test_song_exists(self, sample_song):
        pl = PlaylistADT()
        pl.add_song(sample_song)
        assert pl.song_exists(sample_song['path']) is True
        assert pl.song_exists('/tmp/not-there.mp3') is False

    def test_add_song_at_position_beginning(self, sample_song, sample_song_2):
        pl = PlaylistADT()
        pl.add_song(sample_song)
        pl.add_song_at_position(sample_song_2, 1)
        assert pl.size == 2
        assert pl.head.song['path'] == sample_song_2['path']
        assert pl.tail.song['path'] == sample_song['path']

    def test_add_song_at_position_end(self, sample_song, sample_song_2):
        pl = PlaylistADT()
        pl.add_song(sample_song)
        pl.add_song_at_position(sample_song_2, 2)
        assert pl.size == 2
        assert pl.tail.song['path'] == sample_song_2['path']

    def test_add_song_at_position_middle(self, sample_song, sample_song_2):
        pl = PlaylistADT()
        third = sample_song.copy()
        third['path'] = '/tmp/song3.mp3'
        third['filename'] = 'song3.mp3'

        pl.add_song(sample_song)
        pl.add_song(third)
        pl.add_song_at_position(sample_song_2, 2)

        songs = pl.get_all_songs()
        assert [s['path'] for s in songs] == [
            sample_song['path'],
            sample_song_2['path'],
            third['path'],
        ]

    def test_add_song_at_invalid_position(self, sample_song):
        pl = PlaylistADT()
        assert pl.add_song_at_position(sample_song, 0) is False
        assert pl.add_song_at_position(sample_song, 5) is False
        assert pl.size == 0

    def test_add_duplicate_at_position(self, sample_song):
        pl = PlaylistADT()
        pl.add_song(sample_song)
        assert pl.add_song_at_position(sample_song, 1) is False
        assert pl.size == 1

    def test_remove_song_first(self, sample_song, sample_song_2):
        pl = PlaylistADT()
        pl.add_song(sample_song)
        pl.add_song(sample_song_2)
        removed = pl.remove_song(1)
        assert removed['title'] == 'Song One'
        assert pl.size == 1
        assert pl.head.song['path'] == sample_song_2['path']

    def test_remove_song_last(self, sample_song, sample_song_2):
        pl = PlaylistADT()
        pl.add_song(sample_song)
        pl.add_song(sample_song_2)
        removed = pl.remove_song(2)
        assert removed['title'] == 'Song Two'
        assert pl.size == 1
        assert pl.tail.song['path'] == sample_song['path']

    def test_remove_song_middle(self, sample_song, sample_song_2):
        pl = PlaylistADT()
        third = sample_song.copy()
        third['path'] = '/tmp/song3.mp3'
        third['filename'] = 'song3.mp3'

        pl.add_song(sample_song)
        pl.add_song(sample_song_2)
        pl.add_song(third)

        removed = pl.remove_song(2)
        assert removed['title'] == 'Song Two'
        assert pl.size == 2
        songs = pl.get_all_songs()
        assert [s['path'] for s in songs] == [sample_song['path'], third['path']]

    def test_remove_song_invalid_position(self, sample_song):
        pl = PlaylistADT()
        pl.add_song(sample_song)
        assert pl.remove_song(0) is None
        assert pl.remove_song(10) is None
        assert pl.size == 1

    def test_remove_from_empty(self):
        pl = PlaylistADT()
        assert pl.remove_song(1) is None

    def test_remove_only_song_empties_list(self, sample_song):
        pl = PlaylistADT()
        pl.add_song(sample_song)
        pl.remove_song(1)
        assert pl.size == 0
        assert pl.head is None
        assert pl.tail is None

    def test_move_song_forward(self, sample_song, sample_song_2):
        pl = PlaylistADT()
        pl.add_song(sample_song)
        pl.add_song(sample_song_2)
        assert pl.move_song(1, 2) is True
        assert pl.get_all_songs()[0]['path'] == sample_song_2['path']
        assert pl.get_all_songs()[1]['path'] == sample_song['path']

    def test_move_song_backward(self, sample_song, sample_song_2):
        pl = PlaylistADT()
        pl.add_song(sample_song)
        pl.add_song(sample_song_2)
        assert pl.move_song(2, 1) is True
        assert pl.get_all_songs()[0]['path'] == sample_song_2['path']

    def test_move_same_position_is_noop(self, sample_song):
        pl = PlaylistADT()
        pl.add_song(sample_song)
        assert pl.move_song(1, 1) is True
        assert pl.size == 1

    def test_move_invalid_positions(self, sample_song):
        pl = PlaylistADT()
        pl.add_song(sample_song)
        assert pl.move_song(0, 1) is False
        assert pl.move_song(1, 5) is False

    def test_get_all_songs_order(self, sample_song, sample_song_2):
        pl = PlaylistADT()
        pl.add_song(sample_song)
        pl.add_song(sample_song_2)
        songs = pl.get_all_songs()
        assert len(songs) == 2
        assert songs[0]['path'] == sample_song['path']
        assert songs[1]['path'] == sample_song_2['path']

    def test_play_shuffled_same_length(self, sample_song):
        pl = PlaylistADT()
        for i in range(5):
            s = sample_song.copy()
            s['path'] = f'/tmp/{i}.mp3'
            s['id'] = str(i)
            pl.add_song(s)

        shuffled = pl.play_shuffled()
        assert len(shuffled) == 5
        # All original paths present
        assert {s['path'] for s in shuffled} == {f'/tmp/{i}.mp3' for i in range(5)}

    def test_clear(self, sample_song, sample_song_2):
        pl = PlaylistADT()
        pl.add_song(sample_song)
        pl.add_song(sample_song_2)
        pl.clear()
        assert pl.size == 0
        assert pl.head is None
        assert pl.tail is None



# ============ SONGNODE TESTS ==============================


class TestSongNode:

    def test_node_defaults(self, sample_song):
        node = SongNode(sample_song)
        assert node.song == sample_song
        assert node.next is None
        assert node.prev is None



# ============ MUSIC PLAYER TESTS ==========================


class TestMusicPlayer:

    def test_default_playlist_created(self):
        player = MusicPlayer()
        playlists = player.get_all_playlists()
        names = [p['name'] for p in playlists]
        assert "My Playlist" in names

    def test_create_playlist(self):
        player = MusicPlayer()
        result = player.create_playlist("Test Playlist")
        assert result['name'] == "Test Playlist"
        assert 'id' in result
        assert result['size'] == 0

    def test_delete_playlist(self):
        player = MusicPlayer()
        pl = player.create_playlist("To Delete")
        assert player.delete_playlist(pl['id']) is True
        assert player.delete_playlist(pl['id']) is False

    def test_add_to_playlist(self, sample_song):
        player = MusicPlayer()
        pl = player.create_playlist("Test")
        assert player.add_to_playlist(pl['id'], sample_song) is True

    def test_add_to_nonexistent_playlist(self, sample_song):
        player = MusicPlayer()
        assert player.add_to_playlist("bogus-id", sample_song) is False

    def test_prevent_duplicate_in_playlist(self, sample_song):
        player = MusicPlayer()
        pl = player.create_playlist("Test")
        player.add_to_playlist(pl['id'], sample_song)
        assert player.add_to_playlist(pl['id'], sample_song) is False

    def test_remove_from_playlist(self, sample_song):
        player = MusicPlayer()
        pl = player.create_playlist("Test")
        player.add_to_playlist(pl['id'], sample_song)
        removed = player.remove_from_playlist(pl['id'], 1)
        assert removed is not None
        assert removed['title'] == 'Song One'

    def test_move_in_playlist(self, sample_song, sample_song_2):
        player = MusicPlayer()
        pl = player.create_playlist("Test")
        player.add_to_playlist(pl['id'], sample_song)
        player.add_to_playlist(pl['id'], sample_song_2)
        assert player.move_in_playlist(pl['id'], 1, 2) is True
        songs = player.get_playlist_songs(pl['id'])
        assert songs[0]['path'] == sample_song_2['path']

    def test_get_playlist_songs_empty(self):
        player = MusicPlayer()
        pl = player.create_playlist("Empty")
        assert player.get_playlist_songs(pl['id']) == []

    def test_set_playback_mode(self):
        player = MusicPlayer()
        assert player.set_playback_mode('shuffled') is True
        assert player.playback_mode == 'shuffled'
        assert player.set_playback_mode('sequential') is True
        assert player.set_playback_mode('invalid') is False

    def test_favorites_add(self, sample_song):
        player = MusicPlayer()
        assert player.add_to_favorites(sample_song) is True
        assert len(player.get_favorites()) == 1

    def test_favorites_no_duplicates(self, sample_song):
        player = MusicPlayer()
        player.add_to_favorites(sample_song)
        assert player.add_to_favorites(sample_song) is False
        assert len(player.get_favorites()) == 1

    def test_favorites_remove(self, sample_song):
        player = MusicPlayer()
        player.add_to_favorites(sample_song)
        removed = player.remove_from_favorites(1)
        assert removed is not None
        assert len(player.get_favorites()) == 0

    def test_reset_all_data(self, sample_song):
        player = MusicPlayer()
        pl = player.create_playlist("X")
        player.add_to_playlist(pl['id'], sample_song)
        player.add_to_favorites(sample_song)

        player.reset_all_data()

        assert player.library == []
        assert player.get_favorites() == []
        # Default playlist re-created
        names = [p['name'] for p in player.get_all_playlists()]
        assert "My Playlist" in names



# ============ PLAYLIST PLAYBACK TESTS =====================


class TestPlaylistPlayback:

    def test_set_current_playing_playlist(self):
        player = MusicPlayer()
        pl = player.create_playlist("Test")
        assert player.set_current_playing_playlist(pl['id']) is True
        assert player.set_current_playing_playlist("bogus") is False

    def test_get_current_playlist_song(self, sample_song):
        player = MusicPlayer()
        pl = player.create_playlist("Test")
        player.add_to_playlist(pl['id'], sample_song)
        player.set_current_playing_playlist(pl['id'])
        current = player.get_current_playlist_song()
        assert current is not None
        assert current['title'] == 'Song One'

    def test_play_next_in_playlist(self, sample_song, sample_song_2):
        player = MusicPlayer()
        pl = player.create_playlist("Test")
        player.add_to_playlist(pl['id'], sample_song)
        player.add_to_playlist(pl['id'], sample_song_2)
        player.set_current_playing_playlist(pl['id'])
        next_song = player.play_next_in_playlist()
        assert next_song['path'] == sample_song_2['path']

    def test_play_next_wraps_around(self, sample_song, sample_song_2):
        player = MusicPlayer()
        pl = player.create_playlist("Test")
        player.add_to_playlist(pl['id'], sample_song)
        player.add_to_playlist(pl['id'], sample_song_2)
        player.set_current_playing_playlist(pl['id'])
        player.play_next_in_playlist()  # → song2
        next_song = player.play_next_in_playlist()  # wraps → song1
        assert next_song['path'] == sample_song['path']

    def test_play_previous_in_playlist(self, sample_song, sample_song_2):
        player = MusicPlayer()
        pl = player.create_playlist("Test")
        player.add_to_playlist(pl['id'], sample_song)
        player.add_to_playlist(pl['id'], sample_song_2)
        player.set_current_playing_playlist(pl['id'])
        prev_song = player.play_previous_in_playlist()
        # From index 0 → wraps to last
        assert prev_song['path'] == sample_song_2['path']

    def test_play_song_from_playlist(self, sample_song, sample_song_2):
        player = MusicPlayer()
        pl = player.create_playlist("Test")
        player.add_to_playlist(pl['id'], sample_song)
        player.add_to_playlist(pl['id'], sample_song_2)
        song = player.play_song_from_playlist(pl['id'], 2)
        assert song['path'] == sample_song_2['path']

    def test_play_song_invalid_position(self, sample_song):
        player = MusicPlayer()
        pl = player.create_playlist("Test")
        player.add_to_playlist(pl['id'], sample_song)
        assert player.play_song_from_playlist(pl['id'], 5) is None
        assert player.play_song_from_playlist(pl['id'], 0) is None

    def test_get_current_playlist_info(self, sample_song):
        player = MusicPlayer()
        pl = player.create_playlist("Test")
        player.add_to_playlist(pl['id'], sample_song)
        player.set_current_playing_playlist(pl['id'])
        info = player.get_current_playlist_info()
        assert info is not None
        assert info['name'] == 'Test'
        assert info['index'] == 0
        assert info['size'] == 1



# ============ FILE HASH TESTS =============================


class TestFileHash:

    def test_hash_same_content_same_hash(self, tmp_path):
        player = MusicPlayer()
        f1 = tmp_path / "a.mp3"
        f2 = tmp_path / "b.mp3"
        f1.write_bytes(b"identical bytes")
        f2.write_bytes(b"identical bytes")
        assert player.compute_file_hash(str(f1)) == player.compute_file_hash(str(f2))

    def test_hash_different_content(self, tmp_path):
        player = MusicPlayer()
        f1 = tmp_path / "a.mp3"
        f2 = tmp_path / "b.mp3"
        f1.write_bytes(b"content one")
        f2.write_bytes(b"content two")
        assert player.compute_file_hash(str(f1)) != player.compute_file_hash(str(f2))

    def test_hash_missing_file(self):
        player = MusicPlayer()
        assert player.compute_file_hash("/path/does/not/exist.mp3") is None



# ============ UPLOAD TESTS ================================


class TestUpload:

    def test_upload_no_files(self, client):
        response = client.post('/api/upload_files', data={})
        data = response.get_json()
        assert data['success'] is False

    def test_upload_single_file(self, client, make_fake_upload):
        file_obj, filename = make_fake_upload('test_song.mp3', b'unique audio content 1')
        response = client.post(
            '/api/upload_files',
            data={'files[]': (file_obj, filename), 'folder_path': 'test_folder'},
            content_type='multipart/form-data'
        )
        data = response.get_json()
        assert data['success'] is True
        assert data['count'] == 1
        assert data['total_library_size'] == 1

    def test_upload_duplicate_same_content(self, client, make_fake_upload):
        # First upload
        f1, name1 = make_fake_upload('song.mp3', b'duplicate content')
        client.post(
            '/api/upload_files',
            data={'files[]': (f1, name1), 'folder_path': 'f'},
            content_type='multipart/form-data'
        )

        # Second upload — same content, different name
        f2, name2 = make_fake_upload('copy_of_song.mp3', b'duplicate content')
        response = client.post(
            '/api/upload_files',
            data={'files[]': (f2, name2), 'folder_path': 'f'},
            content_type='multipart/form-data'
        )
        data = response.get_json()
        assert data['success'] is True
        assert data['count'] == 0
        assert len(data['skipped']) == 1
        assert 'Identical' in data['skipped'][0]['reason']

    def test_upload_multiple_new_files(self, client, make_fake_upload):
        f1, n1 = make_fake_upload('a.mp3', b'content a')
        f2, n2 = make_fake_upload('b.mp3', b'content b')
        response = client.post(
            '/api/upload_files',
            data={'files[]': [(f1, n1), (f2, n2)], 'folder_path': 'f'},
            content_type='multipart/form-data'
        )
        data = response.get_json()
        assert data['count'] == 2
        assert data['total_library_size'] == 2
        assert data['skipped'] == []

    def test_upload_mixed_new_and_duplicate(self, client, make_fake_upload):
        # First batch
        f1, n1 = make_fake_upload('orig.mp3', b'orig content')
        client.post(
            '/api/upload_files',
            data={'files[]': (f1, n1), 'folder_path': 'f'},
            content_type='multipart/form-data'
        )

        # Second batch: 1 new + 1 duplicate
        f2, n2 = make_fake_upload('new.mp3', b'new content')
        f3, n3 = make_fake_upload('dup.mp3', b'orig content')  # same as first
        response = client.post(
            '/api/upload_files',
            data={'files[]': [(f2, n2), (f3, n3)], 'folder_path': 'f'},
            content_type='multipart/form-data'
        )
        data = response.get_json()
        assert data['count'] == 1
        assert len(data['skipped']) == 1
        assert data['total_library_size'] == 2



# ============ API ROUTE TESTS =============================


class TestAPIRoutes:

    def test_home_route(self, client):
        response = client.get('/')
        assert response.status_code == 200

    def test_reset_api(self, client):
        response = client.post('/api/reset')
        data = response.get_json()
        assert data['success'] is True

    def test_create_playlist_api(self, client):
        response = client.post(
            '/api/playlists',
            data=json.dumps({'name': 'API Playlist'}),
            content_type='application/json'
        )
        data = response.get_json()
        assert data['success'] is True
        assert data['playlist']['name'] == 'API Playlist'

    def test_get_playlists_api(self, client):
        response = client.get('/api/playlists')
        data = response.get_json()
        assert data['success'] is True
        assert isinstance(data['playlists'], list)

    def test_delete_playlist_api(self, client):
        # Create one
        res = client.post(
            '/api/playlists',
            data=json.dumps({'name': 'To Delete'}),
            content_type='application/json'
        )
        pid = res.get_json()['playlist']['id']

        response = client.delete(f'/api/playlists/{pid}')
        data = response.get_json()
        assert data['success'] is True

    def test_add_to_playlist_api(self, client, sample_song):
        res = client.post(
            '/api/playlists',
            data=json.dumps({'name': 'Test'}),
            content_type='application/json'
        )
        pid = res.get_json()['playlist']['id']

        response = client.post(
            f'/api/playlists/{pid}/songs',
            data=json.dumps({'song': sample_song}),
            content_type='application/json'
        )
        data = response.get_json()
        assert data['success'] is True

    def test_add_duplicate_to_playlist_api(self, client, sample_song):
        res = client.post(
            '/api/playlists',
            data=json.dumps({'name': 'Test'}),
            content_type='application/json'
        )
        pid = res.get_json()['playlist']['id']

        client.post(
            f'/api/playlists/{pid}/songs',
            data=json.dumps({'song': sample_song}),
            content_type='application/json'
        )
        response = client.post(
            f'/api/playlists/{pid}/songs',
            data=json.dumps({'song': sample_song}),
            content_type='application/json'
        )
        data = response.get_json()
        assert data['success'] is False

    def test_get_playlist_songs_api(self, client, sample_song):
        res = client.post(
            '/api/playlists',
            data=json.dumps({'name': 'Test'}),
            content_type='application/json'
        )
        pid = res.get_json()['playlist']['id']

        client.post(
            f'/api/playlists/{pid}/songs',
            data=json.dumps({'song': sample_song}),
            content_type='application/json'
        )

        response = client.get(f'/api/playlists/{pid}/songs')
        data = response.get_json()
        assert data['success'] is True
        assert len(data['songs']) == 1

    def test_remove_from_playlist_api(self, client, sample_song):
        res = client.post(
            '/api/playlists',
            data=json.dumps({'name': 'Test'}),
            content_type='application/json'
        )
        pid = res.get_json()['playlist']['id']

        client.post(
            f'/api/playlists/{pid}/songs',
            data=json.dumps({'song': sample_song}),
            content_type='application/json'
        )

        response = client.delete(f'/api/playlists/{pid}/songs/1')
        data = response.get_json()
        assert data['success'] is True
        assert data['removed_song']['title'] == 'Song One'

    def test_move_in_playlist_api(self, client, sample_song, sample_song_2):
        res = client.post(
            '/api/playlists',
            data=json.dumps({'name': 'Test'}),
            content_type='application/json'
        )
        pid = res.get_json()['playlist']['id']

        client.post(f'/api/playlists/{pid}/songs',
                    data=json.dumps({'song': sample_song}),
                    content_type='application/json')
        client.post(f'/api/playlists/{pid}/songs',
                    data=json.dumps({'song': sample_song_2}),
                    content_type='application/json')

        response = client.post(
            f'/api/playlists/{pid}/move',
            data=json.dumps({'from_position': 1, 'to_position': 2}),
            content_type='application/json'
        )
        data = response.get_json()
        assert data['success'] is True

    def test_play_playlist_api(self, client, sample_song):
        res = client.post(
            '/api/playlists',
            data=json.dumps({'name': 'Test'}),
            content_type='application/json'
        )
        pid = res.get_json()['playlist']['id']
        client.post(f'/api/playlists/{pid}/songs',
                    data=json.dumps({'song': sample_song}),
                    content_type='application/json')

        response = client.post(f'/api/playlists/{pid}/play')
        data = response.get_json()
        assert data['success'] is True
        assert data['song'] is not None

    def test_play_playlist_song_api(self, client, sample_song):
        res = client.post(
            '/api/playlists',
            data=json.dumps({'name': 'Test'}),
            content_type='application/json'
        )
        pid = res.get_json()['playlist']['id']
        client.post(f'/api/playlists/{pid}/songs',
                    data=json.dumps({'song': sample_song}),
                    content_type='application/json')

        response = client.post(f'/api/playlists/{pid}/play/1')
        data = response.get_json()
        assert data['success'] is True
        assert data['song']['title'] == 'Song One'

    def test_play_next_api(self, client, sample_song, sample_song_2):
        res = client.post(
            '/api/playlists',
            data=json.dumps({'name': 'Test'}),
            content_type='application/json'
        )
        pid = res.get_json()['playlist']['id']
        client.post(f'/api/playlists/{pid}/songs',
                    data=json.dumps({'song': sample_song}),
                    content_type='application/json')
        client.post(f'/api/playlists/{pid}/songs',
                    data=json.dumps({'song': sample_song_2}),
                    content_type='application/json')
        client.post(f'/api/playlists/{pid}/play')

        response = client.get('/api/playlists/next')
        data = response.get_json()
        assert data['success'] is True
        assert data['song']['path'] == sample_song_2['path']

    def test_play_previous_api(self, client, sample_song, sample_song_2):
        res = client.post(
            '/api/playlists',
            data=json.dumps({'name': 'Test'}),
            content_type='application/json'
        )
        pid = res.get_json()['playlist']['id']
        client.post(f'/api/playlists/{pid}/songs',
                    data=json.dumps({'song': sample_song}),
                    content_type='application/json')
        client.post(f'/api/playlists/{pid}/songs',
                    data=json.dumps({'song': sample_song_2}),
                    content_type='application/json')
        client.post(f'/api/playlists/{pid}/play')

        response = client.get('/api/playlists/previous')
        data = response.get_json()
        assert data['success'] is True

    def test_current_playlist_api(self, client):
        response = client.get('/api/playlists/current')
        data = response.get_json()
        assert data['success'] is True

    def test_set_playback_mode_api(self, client):
        response = client.post(
            '/api/playback/mode',
            data=json.dumps({'mode': 'shuffled'}),
            content_type='application/json'
        )
        data = response.get_json()
        assert data['success'] is True
        assert data['playback_mode'] == 'shuffled'

    def test_set_playback_mode_invalid(self, client):
        response = client.post(
            '/api/playback/mode',
            data=json.dumps({'mode': 'nonsense'}),
            content_type='application/json'
        )
        data = response.get_json()
        assert data['success'] is False

    # ---- Favorites ----
    def test_add_favorite_api(self, client, sample_song):
        response = client.post(
            '/api/favorites',
            data=json.dumps({'song': sample_song}),
            content_type='application/json'
        )
        data = response.get_json()
        assert data['success'] is True

    def test_get_favorites_api(self, client, sample_song):
        client.post('/api/favorites',
                    data=json.dumps({'song': sample_song}),
                    content_type='application/json')
        response = client.get('/api/favorites')
        data = response.get_json()
        assert data['success'] is True
        assert len(data['favorites']) == 1

    def test_remove_favorite_api(self, client, sample_song):
        client.post('/api/favorites',
                    data=json.dumps({'song': sample_song}),
                    content_type='application/json')
        response = client.delete('/api/favorites/1')
        data = response.get_json()
        assert data['success'] is True

    # ---- Library ----
    def test_get_library_api(self, client):
        response = client.get('/api/library')
        data = response.get_json()
        assert data['success'] is True
        assert isinstance(data['library'], list)

    def test_sort_az_api(self, client):
        response = client.post('/api/sort_az')
        data = response.get_json()
        assert data['success'] is True

    def test_sort_za_api(self, client):
        response = client.post('/api/sort_za')
        data = response.get_json()
        assert data['success'] is True

    def test_restore_order_api(self, client):
        response = client.post('/api/restore_order')
        data = response.get_json()
        assert data['success'] is True

    # ---- Audio serving ----
    def test_audio_route_missing_file(self, client):
        response = client.get('/api/audio/does-not-exist.mp3')
        assert response.status_code == 404



# ============ UTILITY / METADATA TESTS ====================


class TestUtilityMethods:

    def test_parse_filename_artist_and_title(self):
        player = MusicPlayer()
        artist, title = player.parse_filename("Artist Name - Song Title.mp3")
        assert "Artist" in artist
        assert "Song" in title

    def test_parse_filename_with_brackets(self):
        player = MusicPlayer()
        artist, title = player.parse_filename("[Official] Artist - Song (Remix).mp3")
        assert "Artist" in artist
        assert "Song" in title

    def test_parse_filename_with_leading_track_number(self):
        player = MusicPlayer()
        artist, title = player.parse_filename("01 Artist - Song.mp3")
        assert "Artist" in artist
        assert "Song" in title

    def test_parse_filename_no_artist(self):
        player = MusicPlayer()
        artist, title = player.parse_filename("Just A Song.mp3")
        assert artist == "Unknown Artist"
        assert "Just" in title or "Song" in title

    def test_clean_name_capitalizes(self):
        player = MusicPlayer()
        result = player.clean_name("hello_world-test")
        # underscores/dashes → spaces, words capitalized
        assert "Hello" in result
        assert "World" in result
        assert "_" not in result