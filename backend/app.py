import spacy
from flask import Flask, request, jsonify
from flask_cors import CORS
from faster_whisper import WhisperModel
import os

# --- SETUP ---
# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Initialize AI Models (loaded once at startup)
# 1. spaCy for NLP translation
nlp = None
try:
    nlp = spacy.load("en_core_web_sm")
    print("spaCy model loaded successfully.")
except OSError:
    print("spaCy model not found. Please run 'python -m spacy download en_core_web_sm'")

# 2. Whisper for Speech-to-Text
#    Using "tiny.en" for speed. Other options: "base.en", "small.en"
whisper_model = None
try:
    model_size = "tiny.en"
    whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")
    print(f"Whisper model '{model_size}' loaded successfully.")
except Exception as e:
    print(f"Error loading Whisper model: {e}")

# Create a directory for temporary audio files
if not os.path.exists("temp_audio"):
    os.makedirs("temp_audio")
    
# --- NEW, MORE ROBUST TRANSLATION LOGIC ---
def translate_to_isl_gloss(text: str) -> list:
    """
    Translates an English sentence into an ISL gloss sequence by extracting key content words.
    This approach is more robust for a wider variety of sentence structures.
    """
    if not nlp:
        return ["Error: spaCy model not loaded."]
        
    doc = nlp(text.strip().lower())
    
    gloss = []
    
    # Define parts of speech that carry the most meaning
    # NOUN, PROPN (proper noun), VERB, ADJ (adjective), INTJ (interjection)
    important_pos = ["NOUN", "PROPN", "VERB", "ADJ", "INTJ"]
    
    for token in doc:
        # We add the token's base form (lemma) if it's an important POS
        # and not a "stop word" (common words like 'the', 'is', 'a').
        # We make an exception for pronouns, which are stop words but important for context.
        if token.pos_ in important_pos and (not token.is_stop or token.pos_ == 'PRON'):
            # Special case: for "be" verbs, we can often ignore them in ISL gloss
            if token.lemma_ != "be":
                gloss.append(token.lemma_.upper())

    # If the new logic fails to find anything, fallback to the original text
    if not gloss:
        return [word.text.upper() for word in doc if not word.is_punct]

    return gloss

# --- API ENDPOINTS ---
@app.route('/transcribe', methods=['POST'])
def transcribe_audio():
    """
    API endpoint to handle audio transcription and translation.
    Expects audio file data.
    """
    if 'audio_data' not in request.files:
        return jsonify({"error": "No audio file part"}), 400
    
    audio_file = request.files['audio_data']
    
    if audio_file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    try:
        # Save the audio file temporarily
        temp_path = os.path.join("temp_audio", "temp_recording.webm")
        audio_file.save(temp_path)

        # Transcribe audio to text using Whisper
        if not whisper_model:
            return jsonify({"error": "Whisper model not loaded"}), 500
            
        segments, _ = whisper_model.transcribe(temp_path, beam_size=5)
        transcribed_text = "".join(segment.text for segment in segments).strip()
        
        if not transcribed_text:
             return jsonify({"transcribed_text": "", "gloss": []})

        # Translate the transcribed text to ISL gloss
        isl_gloss = translate_to_isl_gloss(transcribed_text)
        
        # Clean up the temporary file
        os.remove(temp_path)
        
        return jsonify({"transcribed_text": transcribed_text, "gloss": isl_gloss})

    except Exception as e:
        print(f"An error occurred: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)

