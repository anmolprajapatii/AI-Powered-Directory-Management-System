from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
import os
import shutil
import speech_recognition as sr
from threading import Thread, Lock
import time
import atexit

app = Flask(__name__, template_folder='templates', static_folder='static')

# Configure CORS
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Voice control variables
voice_lock = Lock()
current_voice_command = None
listening_active = True

def voice_listener():
    global current_voice_command, listening_active
    
    recognizer = sr.Recognizer()
    microphone = sr.Microphone()
    
    # Adjust for ambient noise
    with microphone as source:
        recognizer.adjust_for_ambient_noise(source, duration=3)
    
    while listening_active:
        try:
            print("\nListening for voice command... (Say 'create', 'delete', 'move', or 'organize')")
            
            with microphone as source:
                audio = recognizer.listen(source, timeout=10, phrase_time_limit=10 )
            
            command = recognizer.recognize_google(audio).lower()
            print(f"Detected command: {command}")
            
            with voice_lock:
                if 'create' in command:
                    current_voice_command = 'create'
                elif 'delete' in command:
                    current_voice_command = 'delete'
                elif 'moved' in command:
                    current_voice_command = 'move'
                elif 'organize' in command or 'organise' in command:
                    current_voice_command = 'organize'
                else:
                    print(f"Unknown command: {command}")
                
        except sr.WaitTimeoutError:
            continue
        except sr.UnknownValueError:
            print("Could not understand audio")
        except sr.RequestError as e:
            print(f"Could not request results; {e}")
        except Exception as e:
            print(f"Error in voice listener: {e}")

# Start the voice listener thread
voice_thread = Thread(target=voice_listener)
voice_thread.daemon = True
voice_thread.start()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                             'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/api/voice_command', methods=['GET'])
def get_voice_command():
    global current_voice_command
    with voice_lock:
        if current_voice_command:
            command = current_voice_command
            current_voice_command = None  # Reset after reading
            return jsonify({
                "success": True, 
                "command": command,
                "message": f"Voice command detected: {command}"
            })
        return jsonify({"success": False, "command": None})

@app.route('/api/directory', methods=['POST', 'OPTIONS'])
def handle_directory():
    if request.method == 'OPTIONS':
        return jsonify({"success": True}), 200
        
    try:
        data = request.get_json()
        action = data.get('action')
        path = data.get('path', '')
        name = data.get('name', '')
        dest = data.get('dest', '')

        # Validate paths
        if action in ['delete', 'move', 'organize']:
            if not os.path.exists(path):
                return jsonify({"success": False, "message": "Path does not exist"}), 404
            if action == 'move' and not dest:
                return jsonify({"success": False, "message": "Destination path required"}), 400

        if action == 'create':
            full_path = os.path.join(path, name)
            os.makedirs(full_path, exist_ok=True)
            return jsonify({"success": True, "message": f"Created directory: {full_path}"})

        elif action == 'delete':
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            return jsonify({"success": True, "message": f"Deleted: {path}"})

        elif action == 'move':
            shutil.move(path, os.path.join(dest, os.path.basename(path)))
            return jsonify({"success": True, "message": f"Moved to: {dest}"})

        elif action == 'organize':
            categories = {
                'Images': ['.png', '.jpg', '.jpeg', '.gif', '.webp'],
                'Documents': ['.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt'],
                'Archives': ['.zip', '.rar', '.7z', '.tar', '.gz'],
                'Code': ['.py', '.js', '.html', '.css', '.java', '.cpp'],
                'Media': ['.mp3', '.mp4', '.avi', '.mkv', '.mov']
            }

            # Create category directories
            for category in categories:
                os.makedirs(os.path.join(path, category), exist_ok=True)

            moved_files = 0
            for item in os.listdir(path):
                item_path = os.path.join(path, item)
                if os.path.isfile(item_path):
                    ext = os.path.splitext(item)[1].lower()
                    for category, extensions in categories.items():
                        if ext in extensions:
                            shutil.move(item_path, os.path.join(path, category, item))
                            moved_files += 1
                            break

            return jsonify({
                "success": True,
                "message": f"Organized {moved_files} files into categories",
                "categories": list(categories.keys())
            })

        return jsonify({"success": False, "message": "Invalid action"}), 400

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

def cleanup():
    global listening_active
    listening_active = False
    voice_thread.join(timeout=1)

atexit.register(cleanup)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
