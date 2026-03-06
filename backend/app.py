"""
Viral Shorts Automation Tool
=============================
TikTok/Kwai থেকে viral video নিয়ে YouTube Shorts বানানোর tool
"""

import os
import re
import json
import uuid
import shutil
import logging
import subprocess
import zipfile
import tempfile
import requests
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'viral-shorts-secret-2024')
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

CORS(app, origins=["*"], supports_credentials=True)

# Create directories
for folder in ['uploads', 'uploads/videos', 'uploads/audio', 'uploads/output', 'uploads/zips', 'uploads/temp']:
    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), folder), exist_ok=True)

GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')

# ==================== AI SERVICE ====================

class AIService:
    def __init__(self):
        self.api_key = GROQ_API_KEY
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"

    def generate_metadata(self, video_description="cooking food viral"):
        logger.info(f"Generating metadata, API key: {'set' if self.api_key else 'MISSING'}")
        if not self.api_key:
            logger.warning("GROQ API key missing!")
            return self._fallback_metadata()
        try:
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            prompt = f"""তুমি একজন বাংলা YouTube Shorts বিশেষজ্ঞ।
এই ভিডিওর জন্য metadata তৈরি করো: {video_description}

শুধুমাত্র এই JSON format এ দাও, অন্য কিছু লিখবে না:
{{
    "title": "আকর্ষণীয় বাংলা title (৬০ character এর মধ্যে)",
    "description": "বাংলা description ৩-৪ লাইন SEO optimized",
    "tags": ["রান্না", "cooking", "viral", "shorts", "food", "bangladesh", "খাবার", "ভাইরাল"],
    "hashtags": "#রান্না #ভাইরাল #shorts #ytshorts #খাবার #cooking #food #bangladesh"
}}"""
            data = {
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 600,
                "temperature": 0.8
            }
            response = requests.post(self.base_url, headers=headers, json=data, timeout=30)
            result = response.json()
            logger.info(f"GROQ response: {result.get('choices', [{}])[0].get('message', {}).get('content', '')[:100]}")
            content = result['choices'][0]['message']['content']
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                logger.info(f"AI metadata generated: {parsed.get('title', '')}")
                return parsed
            logger.warning("Could not parse JSON from AI response")
        except Exception as e:
            logger.error(f"AI error: {e}")
        return self._fallback_metadata()

    def _fallback_metadata(self):
        titles = [
            "😱 অবিশ্বাস্য রান্না দেখে চোখ ফেরানো যাচ্ছে না!",
            "🔥 এত বড় মাছ! একবার দেখলে ভুলবেন না",
            "😍 পৃথিবীর সবচেয়ে সুন্দর রান্না",
            "🤯 এভাবে রান্না করা সম্ভব? অবাক হয়ে যাবেন!",
            "👨‍🍳 মাস্টার শেফের রান্না দেখুন",
        ]
        import random
        return {
            "title": random.choice(titles),
            "description": "অসাধারণ রান্নার ভিডিও! লাইক দিন এবং সাবস্ক্রাইব করুন 🔔\n\n#রান্না #ভাইরাল #shorts",
            "tags": ["রান্না", "cooking", "viral", "shorts", "food", "bangladesh", "খাবার"],
            "hashtags": "#রান্না #ভাইরাল #shorts #ytshorts #খাবার #cooking #food"
        }

ai_service = AIService()

# ==================== VIDEO DOWNLOADER ====================

class VideoDownloader:

    def download_tiktok(self, url, output_path):
        """Download TikTok video without watermark"""
        try:
            # First resolve short URLs (vt.tiktok.com, vm.tiktok.com)
            if 'vt.tiktok.com' in url or 'vm.tiktok.com' in url:
                try:
                    r = requests.get(url, allow_redirects=True, timeout=15,
                                   headers={'User-Agent': 'Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36'})
                    url = r.url
                    logger.info(f"Resolved URL: {url}")
                except:
                    pass

            # Method 1: yt-dlp best mp4
            base = output_path.replace('.mp4', '')
            cmd = [
                'yt-dlp',
                '--no-check-certificates',
                '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                '--merge-output-format', 'mp4',
                '--no-playlist',
                '-o', base + '.%(ext)s',
                url
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            
            # Find the downloaded file
            for ext in ['.mp4', '.webm', '.mkv', '.mov']:
                if os.path.exists(base + ext):
                    if base + ext != output_path:
                        shutil.move(base + ext, output_path)
                    return True, output_path
            
            # Method 2: simple best
            cmd2 = ['yt-dlp', '--no-check-certificates', '-f', 'best', '-o', output_path, url]
            result2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=180)
            if os.path.exists(output_path):
                return True, output_path
            
            return False, result.stderr or result2.stderr
        except Exception as e:
            return False, str(e)

    def download_kwai(self, url, output_path):
        """Download Kwai video"""
        try:
            # Step 1: Follow redirect to get real URL
            response = requests.get(url, allow_redirects=True, timeout=30, 
                                   headers={'User-Agent': 'Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36'})
            final_url = response.url
            
            # Step 2: Get page content and find mp4 URLs
            content = response.text
            mp4_urls = re.findall(r'https://[^"\'<>\s]*\.mp4[^"\'<>\s]*', content)
            
            if not mp4_urls:
                # Try curl approach
                result = subprocess.run(
                    ['curl', '-L', url, '-o', '/dev/null', '-w', '%{url_effective}', '-s'],
                    capture_output=True, text=True, timeout=30
                )
                if result.returncode == 0:
                    real_url = result.stdout.strip()
                    # Fetch the real page
                    resp2 = requests.get(real_url, timeout=30,
                                        headers={'User-Agent': 'Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36'})
                    mp4_urls = re.findall(r'https://[^"\'<>\s]*\.mp4[^"\'<>\s]*', resp2.text)
            
            if mp4_urls:
                # Download the first mp4
                mp4_url = mp4_urls[0]
                r = requests.get(mp4_url, stream=True, timeout=60,
                                headers={'User-Agent': 'Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36',
                                        'Referer': 'https://www.kwai.com/'})
                with open(output_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                if os.path.getsize(output_path) > 10000:
                    return True, output_path
            
            return False, "Could not find video URL"
        except Exception as e:
            return False, str(e)

    def search_tiktok(self, keyword, count=10):
        """Search TikTok videos by keyword"""
        try:
            # Use yt-dlp to search
            search_url = f"https://www.tiktok.com/search?q={keyword}"
            cmd = [
                'yt-dlp',
                '--no-download',
                '--print', '%(id)s|||%(title)s|||%(thumbnail)s|||%(duration)s|||%(webpage_url)s',
                '--playlist-end', str(count),
                f'ytsearch{count}:{keyword} tiktok cooking food',
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            videos = []
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if '|||' in line:
                        parts = line.split('|||')
                        if len(parts) >= 4:
                            videos.append({
                                'id': parts[0],
                                'title': parts[1],
                                'thumbnail': parts[2],
                                'duration': parts[3],
                                'url': parts[4] if len(parts) > 4 else ''
                            })
            
            # If yt-dlp search fails, try direct TikTok hashtag
            if not videos:
                videos = self._get_tiktok_hashtag(keyword)
            
            return videos
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []

    def _get_tiktok_hashtag(self, keyword):
        """Get videos from TikTok hashtag"""
        try:
            hashtag = keyword.replace(' ', '').lower()
            cmd = [
                'yt-dlp',
                '--no-download', 
                '--print', '%(id)s|||%(title)s|||%(thumbnail)s|||%(duration)s|||%(webpage_url)s',
                '--playlist-end', '10',
                f'https://www.tiktok.com/tag/{hashtag}'
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            videos = []
            for line in result.stdout.strip().split('\n'):
                if '|||' in line:
                    parts = line.split('|||')
                    if len(parts) >= 4:
                        videos.append({
                            'id': parts[0],
                            'title': parts[1],
                            'thumbnail': parts[2] if len(parts) > 2 else '',
                            'duration': parts[3] if len(parts) > 3 else '0',
                            'url': parts[4] if len(parts) > 4 else ''
                        })
            return videos
        except:
            return []

downloader = VideoDownloader()

# ==================== VIDEO PROCESSOR ====================

class VideoProcessor:

    def merge_videos(self, video_paths, output_path):
        """Merge multiple videos"""
        try:
            # Create file list for ffmpeg
            list_file = output_path.replace('.mp4', '_list.txt')
            with open(list_file, 'w') as f:
                for vp in video_paths:
                    f.write(f"file '{vp}'\n")
            
            cmd = [
                'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
                '-i', list_file,
                '-c:v', 'libx264', '-c:a', 'aac',
                '-vf', 'scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2',
                output_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            os.remove(list_file)
            
            if result.returncode == 0:
                return True, output_path
            return False, result.stderr
        except Exception as e:
            return False, str(e)

    def mute_video(self, input_path, output_path):
        """Remove audio from video"""
        try:
            cmd = ['ffmpeg', '-y', '-i', input_path, '-an', '-c:v', 'copy', output_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                return True, output_path
            return False, result.stderr
        except Exception as e:
            return False, str(e)

    def add_audio(self, video_path, audio_path, output_path):
        """Add audio to muted video"""
        try:
            # Get video duration
            probe_cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', video_path]
            probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
            duration = 60  # default
            if probe_result.returncode == 0:
                info = json.loads(probe_result.stdout)
                duration = float(info.get('format', {}).get('duration', 60))

            cmd = [
                'ffmpeg', '-y',
                '-i', video_path,
                '-i', audio_path,
                '-c:v', 'copy',
                '-c:a', 'aac',
                '-map', '0:v:0',
                '-map', '1:a:0',
                '-shortest',
                '-t', str(duration),
                output_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                return True, output_path
            return False, result.stderr
        except Exception as e:
            return False, str(e)

    def download_audio_from_youtube(self, url, output_path):
        """Download audio from YouTube"""
        try:
            cmd = [
                'yt-dlp',
                '-f', 'bestaudio',
                '-x', '--audio-format', 'mp3',
                '-o', output_path.replace('.mp3', ''),
                url
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            # Find downloaded file
            base = output_path.replace('.mp3', '')
            for ext in ['.mp3', '.m4a', '.webm', '.opus']:
                if os.path.exists(base + ext):
                    if base + ext != output_path:
                        shutil.move(base + ext, output_path)
                    return True, output_path
            
            return False, result.stderr
        except Exception as e:
            return False, str(e)

    def crop_to_shorts(self, input_path, output_path):
        """Crop video to 9:16 for Shorts"""
        try:
            cmd = [
                'ffmpeg', '-y', '-i', input_path,
                '-vf', 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920',
                '-c:a', 'copy',
                output_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                return True, output_path
            return False, result.stderr
        except Exception as e:
            return False, str(e)

processor = VideoProcessor()

# ==================== GOOGLE DRIVE ====================

class DriveService:
    def upload_file(self, file_path, folder_id=None):
        """Upload file to Google Drive"""
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload

            creds_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'credentials', 'drive_token.json')
            if not os.path.exists(creds_file):
                return False, "Drive not connected"

            creds = Credentials.from_authorized_user_file(creds_file)
            service = build('drive', 'v3', credentials=creds)

            file_metadata = {'name': os.path.basename(file_path)}
            if folder_id:
                file_metadata['parents'] = [folder_id]

            media = MediaFileUpload(file_path, resumable=True)
            file = service.files().create(body=file_metadata, media_body=media, fields='id,webViewLink').execute()
            return True, file.get('webViewLink', '')
        except Exception as e:
            return False, str(e)

drive_service = DriveService()

# ==================== YOUTUBE UPLOADER ====================

class YouTubeUploader:
    def upload(self, video_path, title, description, tags):
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload

            creds_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'credentials', 'youtube_token.json')
            if not os.path.exists(creds_file):
                return False, "YouTube not connected"

            creds = Credentials.from_authorized_user_file(creds_file)
            youtube = build('youtube', 'v3', credentials=creds)

            body = {
                'snippet': {
                    'title': title[:100],
                    'description': description,
                    'tags': tags[:10],
                    'categoryId': '22',
                    'defaultLanguage': 'bn'
                },
                'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False}
            }

            media = MediaFileUpload(video_path, mimetype='video/mp4', resumable=True)
            request = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=media)

            response = None
            while response is None:
                status, response = request.next_chunk()

            return True, f"https://youtube.com/watch?v={response['id']}"
        except Exception as e:
            return False, str(e)

youtube_uploader = YouTubeUploader()

# ==================== STATE MANAGEMENT ====================

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'state.json')

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        'audio_links': [],
        'schedule': {'times': ['12:00', '20:00'], 'enabled': False},
        'drive_folder_id': '',
        'youtube_connected': False,
        'drive_connected': False,
        'processed_videos': [],
        'upload_queue': []
    }

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

# ==================== ROUTES ====================

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    dist_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'frontend', 'dist')
    if path and os.path.exists(os.path.join(dist_dir, path)):
        return send_from_directory(dist_dir, path)
    return send_from_directory(dist_dir, 'index.html')

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'timestamp': datetime.utcnow().isoformat()})

@app.route('/api/search', methods=['POST'])
def search_videos():
    data = request.json
    keyword = data.get('keyword', 'cooking food')
    source = data.get('source', 'tiktok')
    
    try:
        if source == 'tiktok':
            videos = downloader.search_tiktok(keyword, count=10)
        else:
            videos = []
        
        return jsonify({'success': True, 'videos': videos})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/download', methods=['POST'])
def download_video():
    data = request.json
    url = data.get('url', '')
    source = data.get('source', 'tiktok')
    
    if not url:
        return jsonify({'success': False, 'error': 'URL required'}), 400
    
    video_id = str(uuid.uuid4())[:8]
    output_path = os.path.join(app.config['UPLOAD_FOLDER'], 'videos', f'{video_id}.mp4')
    
    if source == 'tiktok':
        success, result = downloader.download_tiktok(url, output_path)
    else:
        success, result = downloader.download_kwai(url, output_path)
    
    if success and os.path.exists(output_path):
        return jsonify({
            'success': True,
            'video_id': video_id,
            'path': output_path,
            'size': os.path.getsize(output_path)
        })
    return jsonify({'success': False, 'error': str(result)}), 400

@app.route('/api/merge', methods=['POST'])
def merge_videos():
    data = request.json
    video_ids = data.get('video_ids', [])
    
    if len(video_ids) < 2:
        return jsonify({'success': False, 'error': 'Need at least 2 videos'}), 400
    
    video_paths = []
    for vid in video_ids:
        path = os.path.join(app.config['UPLOAD_FOLDER'], 'videos', f'{vid}.mp4')
        if os.path.exists(path):
            video_paths.append(path)
    
    if len(video_paths) < 2:
        return jsonify({'success': False, 'error': 'Videos not found'}), 400
    
    merged_id = str(uuid.uuid4())[:8]
    output_path = os.path.join(app.config['UPLOAD_FOLDER'], 'videos', f'merged_{merged_id}.mp4')
    
    success, result = processor.merge_videos(video_paths, output_path)
    if success:
        return jsonify({'success': True, 'video_id': f'merged_{merged_id}'})
    return jsonify({'success': False, 'error': result}), 400

@app.route('/api/process', methods=['POST'])
def process_video():
    """Mute video + add audio + crop to shorts format"""
    data = request.json
    video_id = data.get('video_id', '')
    audio_url = data.get('audio_url', '')
    description = data.get('description', 'viral cooking food bangladesh shorts')
    
    if not video_id:
        return jsonify({'success': False, 'error': 'video_id required'}), 400
    
    # Check multiple folders for the video
    video_path = None
    for folder in ['videos', 'temp']:
        p = os.path.join(app.config['UPLOAD_FOLDER'], folder, f'{video_id}.mp4')
        if os.path.exists(p):
            video_path = p
            break
    
    if not video_path:
        return jsonify({'success': False, 'error': f'Video not found: {video_id}'}), 404
    
    output_id = str(uuid.uuid4())[:8]
    
    try:
        # Step 1: Mute video
        muted_path = os.path.join(app.config['UPLOAD_FOLDER'], 'temp', f'muted_{output_id}.mp4')
        success, result = processor.mute_video(video_path, muted_path)
        if not success:
            logger.error(f"Mute failed: {result}")
            # Try to use original
            muted_path = video_path

        # Step 2: Crop to 9:16
        cropped_path = os.path.join(app.config['UPLOAD_FOLDER'], 'temp', f'cropped_{output_id}.mp4')
        success, result = processor.crop_to_shorts(muted_path, cropped_path)
        if not success:
            logger.warning(f"Crop failed, using muted: {result}")
            cropped_path = muted_path

        final_path = os.path.join(app.config['UPLOAD_FOLDER'], 'output', f'final_{output_id}.mp4')

        # Step 3: Add audio if provided
        if audio_url:
            audio_path = os.path.join(app.config['UPLOAD_FOLDER'], 'audio', f'audio_{output_id}.mp3')
            audio_success, audio_result = processor.download_audio_from_youtube(audio_url, audio_path)
            
            if audio_success:
                success, result = processor.add_audio(cropped_path, audio_path, final_path)
                if not success:
                    logger.warning(f"Add audio failed: {result}")
                    shutil.copy(cropped_path, final_path)
            else:
                logger.warning(f"Audio download failed: {audio_result}")
                shutil.copy(cropped_path, final_path)
        else:
            shutil.copy(cropped_path, final_path)

        # Step 4: Generate AI metadata
        metadata = ai_service.generate_metadata(description)
        logger.info(f"Final metadata title: {metadata.get('title', 'N/A')}")
        
        return jsonify({
            'success': True,
            'output_id': f'final_{output_id}',
            'metadata': metadata
        })
        
    except Exception as e:
        logger.error(f"Process error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/preview/<video_id>')
def preview_video(video_id):
    # Check multiple folders
    for folder in ['output', 'videos', 'temp']:
        path = os.path.join(app.config['UPLOAD_FOLDER'], folder, f'{video_id}.mp4')
        if os.path.exists(path):
            return send_file(path, mimetype='video/mp4')
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/zip', methods=['POST'])
def create_zip():
    """ZIP selected output videos"""
    data = request.json
    output_ids = data.get('output_ids', [])
    
    if not output_ids:
        return jsonify({'success': False, 'error': 'No videos selected'}), 400
    
    zip_id = str(uuid.uuid4())[:8]
    zip_path = os.path.join(app.config['UPLOAD_FOLDER'], 'zips', f'shorts_{zip_id}.zip')
    
    with zipfile.ZipFile(zip_path, 'w') as zf:
        for output_id in output_ids:
            video_path = os.path.join(app.config['UPLOAD_FOLDER'], 'output', f'{output_id}.mp4')
            if os.path.exists(video_path):
                zf.write(video_path, f'{output_id}.mp4')
    
    return send_file(zip_path, as_attachment=True, download_name=f'viral_shorts_{zip_id}.zip')

@app.route('/api/upload-to-drive', methods=['POST'])
def upload_to_drive():
    data = request.json
    output_ids = data.get('output_ids', [])
    
    state = load_state()
    folder_id = state.get('drive_folder_id', '')
    
    results = []
    for output_id in output_ids:
        video_path = os.path.join(app.config['UPLOAD_FOLDER'], 'output', f'{output_id}.mp4')
        if os.path.exists(video_path):
            success, result = drive_service.upload_file(video_path, folder_id)
            results.append({'id': output_id, 'success': success, 'url': result})
    
    return jsonify({'success': True, 'results': results})

@app.route('/api/upload-to-youtube', methods=['POST'])
def upload_to_youtube():
    data = request.json
    output_id = data.get('output_id', '')
    metadata = data.get('metadata', {})
    
    video_path = os.path.join(app.config['UPLOAD_FOLDER'], 'output', f'{output_id}.mp4')
    if not os.path.exists(video_path):
        return jsonify({'success': False, 'error': 'Video not found'}), 404
    
    title = metadata.get('title', 'Viral Shorts')
    description = metadata.get('description', '')
    tags = metadata.get('tags', [])
    
    success, result = youtube_uploader.upload(video_path, title, description, tags)
    
    if success:
        state = load_state()
        state['upload_queue'].append({
            'id': output_id,
            'title': title,
            'url': result,
            'uploaded_at': datetime.utcnow().isoformat()
        })
        save_state(state)
        return jsonify({'success': True, 'url': result})
    
    return jsonify({'success': False, 'error': result}), 400

@app.route('/api/state', methods=['GET'])
def get_state():
    return jsonify(load_state())

@app.route('/api/state', methods=['POST'])
def update_state():
    data = request.json
    state = load_state()
    state.update(data)
    save_state(state)
    return jsonify({'success': True})

@app.route('/api/add-audio-link', methods=['POST'])
def add_audio_link():
    data = request.json
    url = data.get('url', '')
    name = data.get('name', 'Audio')
    
    if not url:
        return jsonify({'success': False, 'error': 'URL required'}), 400
    
    state = load_state()
    state['audio_links'].append({'url': url, 'name': name, 'id': str(uuid.uuid4())[:8]})
    save_state(state)
    return jsonify({'success': True})

@app.route('/api/audio-links', methods=['GET'])
def get_audio_links():
    state = load_state()
    return jsonify({'audio_links': state.get('audio_links', [])})

@app.route('/api/auto-pilot', methods=['POST'])
def auto_pilot():
    """Pick random video from drive + random audio + upload"""
    data = request.json
    state = load_state()
    
    audio_links = state.get('audio_links', [])
    if not audio_links:
        return jsonify({'success': False, 'error': 'No audio links saved'}), 400
    
    import random
    audio = random.choice(audio_links)
    
    # Get uploaded videos list
    output_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'output')
    videos = [f for f in os.listdir(output_folder) if f.endswith('.mp4')]
    
    if not videos:
        return jsonify({'success': False, 'error': 'No videos in output folder'}), 400
    
    video_file = random.choice(videos)
    video_id = video_file.replace('.mp4', '')
    
    # Process with random audio
    result_data = process_video_internal(video_id, audio['url'])
    
    if result_data['success']:
        metadata = ai_service.generate_metadata()
        success, url = youtube_uploader.upload(
            result_data['path'],
            metadata['title'],
            metadata['description'],
            metadata['tags']
        )
        if success:
            return jsonify({'success': True, 'url': url, 'metadata': metadata})
    
    return jsonify({'success': False, 'error': 'Auto pilot failed'})

def process_video_internal(video_id, audio_url):
    video_path = os.path.join(app.config['UPLOAD_FOLDER'], 'output', f'{video_id}.mp4')
    if not os.path.exists(video_path):
        return {'success': False}
    
    output_id = str(uuid.uuid4())[:8]
    audio_path = os.path.join(app.config['UPLOAD_FOLDER'], 'audio', f'audio_{output_id}.mp3')
    final_path = os.path.join(app.config['UPLOAD_FOLDER'], 'output', f'autopilot_{output_id}.mp4')
    
    success, _ = processor.download_audio_from_youtube(audio_url, audio_path)
    if success:
        success, _ = processor.add_audio(video_path, audio_path, final_path)
        if success:
            return {'success': True, 'path': final_path}
    return {'success': False}

# ==================== OAUTH ROUTES ====================

CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', '682704644251-h27c3e55oidg73cfqq6b318o4hgdqnet.apps.googleusercontent.com')
CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET', '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')
YOUTUBE_SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube'
]

@app.route('/oauth/login')
def oauth_login():
    try:
        from google_auth_oauthlib.flow import Flow
        base_url = os.getenv('BASE_URL', request.host_url.rstrip('/'))
        redirect_uri = f"{base_url}/oauth/callback"
        
        client_config = {
            "web": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uris": [redirect_uri],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token"
            }
        }
        
        flow = Flow.from_client_config(client_config, scopes=YOUTUBE_SCOPES, redirect_uri=redirect_uri)
        auth_url, state = flow.authorization_url(prompt='consent', access_type='offline')
        
        # Save state
        from flask import session
        session['oauth_state'] = state
        session['redirect_uri'] = redirect_uri
        
        return jsonify({'auth_url': auth_url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/oauth/callback')
def oauth_callback():
    try:
        from google_auth_oauthlib.flow import Flow
        from flask import session, redirect
        
        redirect_uri = session.get('redirect_uri', request.host_url.rstrip('/') + '/oauth/callback')
        
        client_config = {
            "web": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uris": [redirect_uri],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token"
            }
        }
        
        flow = Flow.from_client_config(client_config, scopes=YOUTUBE_SCOPES, redirect_uri=redirect_uri)
        flow.fetch_token(authorization_response=request.url)
        creds = flow.credentials
        
        os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'credentials'), exist_ok=True)
        token_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'credentials', 'youtube_token.json')
        
        token_data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes)
        }
        
        with open(token_path, 'w') as f:
            json.dump(token_data, f)
        
        # Update state
        state = load_state()
        state['youtube_connected'] = True
        save_state(state)
        
        return """
        <html><body style="background:#0a0a0f;color:#00e676;font-family:sans-serif;text-align:center;padding:60px">
        <h2>✅ YouTube Connected!</h2>
        <p style="color:#f0f0f5">সফলভাবে connect হয়েছে!</p>
        <script>setTimeout(()=>window.close(),2000)</script>
        </body></html>
        """
    except Exception as e:
        return f"""
        <html><body style="background:#0a0a0f;color:#ff3d5a;font-family:sans-serif;text-align:center;padding:60px">
        <h2>❌ Error</h2><p style="color:#f0f0f5">{str(e)}</p>
        </body></html>
        """

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
