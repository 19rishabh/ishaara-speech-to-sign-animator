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
    
# --- REVISED, MORE ACCURATE TRANSLATION LOGIC ---
def translate_to_isl_gloss(text: str) -> list:
    """
    Translates an English sentence into an ISL gloss sequence by extracting key content words,
    handling negation, and mapping synonyms.
    """
    if not nlp:
        return ["Error: spaCy model not loaded."]
        
    doc = nlp(text.strip().lower())
    
    gloss = []
    
    # This dictionary maps English lemmas to a primary ISL sign concept.
    # This is where linguistic exceptions are handled.
    isl_synonym_map = {
        "FOOD": "EAT",
        "HOME": "HOUSE",
        "MINE": "MY",
        "MYSELF": "I",
        "HEY": "HELLO",
        "HI": "HELLO"
        # This map can be expanded as more synonyms are identified.
    }
    
    important_pos = ["NOUN", "PROPN", "VERB", "ADJ", "INTJ", "PRON", "ADV"]
    
    for token in doc:
        # Check for negation separately
        if token.dep_ == "neg":
            gloss.append("NOT")
            continue

        if token.pos_ in important_pos:
            if token.lemma_ != "be":
                # Special handling for "don't" which can be missed
                if token.text == "dont":
                    gloss.append("NOT")
                else:
                    gloss.append(token.lemma_.upper())

    # If the logic fails to find anything, fallback to the original text
    if not gloss:
        return [word.text.upper() for word in doc if not word.is_punct]

    # --- NEW: Apply the synonym map to the generated gloss ---
    # This step ensures that words like 'FOOD' are mapped to 'EAT' before being sent.
    final_gloss = [isl_synonym_map.get(word, word) for word in gloss]

    return final_gloss

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

