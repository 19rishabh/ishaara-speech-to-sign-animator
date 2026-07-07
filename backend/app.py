import spacy
from flask import Flask, request, jsonify
from flask_cors import CORS
from faster_whisper import WhisperModel
import os

# --- SETUP ---
app = Flask(__name__)
CORS(app)

nlp = None
try:
    nlp = spacy.load("en_core_web_sm")
    print("spaCy model loaded successfully.")
except OSError:
    print("spaCy model not found. Please run 'python -m spacy download en_core_web_sm'")

whisper_model = None
try:
    model_size = "tiny.en"
    whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")
    print(f"Whisper model '{model_size}' loaded successfully.")
except Exception as e:
    print(f"Error loading Whisper model: {e}")

if not os.path.exists("temp_audio"):
    os.makedirs("temp_audio")
    
# --- AI-Guided Reordering Engine ---
def translate_to_isl_gloss(text: str) -> list:
    """
    Translates an English sentence into a grammatically-ordered ISL gloss sequence
    using a "bucket" sorting method based on spaCy's linguistic analysis.
    """
    if not nlp:
        return ["Error: nlp model not loaded"]
        
    doc = nlp(text.strip().lower())
    
    buckets = {
        "TIME": [], "PLACE": [], "SUBJECT": [], "OBJECT": [], "VERB": [],
        "NEGATION": [], "WH_QUESTION": [], "UNCLASSIFIED": []
    }
    
    isl_synonym_map = {
        "HOME": "HOUSE", "MINE": "MY", "MYSELF": "I",
        "ME": "I", "HEY": "HELLO", "HI": "HELLO", "SEE": "LOOK"
    }

    noun_map = {}

    # --- 2. Linguistic Triage: Sort tokens into buckets (General Rules) ---
    for token in doc:
        lemma = token.lemma_.upper()

        if token.pos_ == 'DET' or token.lemma_ == 'be' or token.pos_ == 'AUX':
            continue
            
        if token.dep_ == 'neg' or token.text == 'dont':
            buckets["NEGATION"].append("NOT")
            continue
            
        if token.tag_ in ['WDT', 'WP', 'WP$', 'WRB']:
            buckets["WH_QUESTION"].append(lemma)
            continue
            
        if token.ent_type_ == 'TIME' or token.lemma_ in ['tomorrow', 'yesterday', 'now', 'today']:
            buckets["TIME"].append(lemma)
            continue
            
        if token.lemma_ == 'home' or token.ent_type_ in ['GPE', 'LOC']:
            buckets["PLACE"].append(lemma)
            continue
            
        if 'nsubj' in token.dep_:
            buckets["SUBJECT"].append(lemma)
            noun_map[token.i] = (lemma, "SUBJECT") 
            continue
            
        if 'dobj' in token.dep_ or 'pobj' in token.dep_:
            buckets["OBJECT"].append(lemma)
            noun_map[token.i] = (lemma, "OBJECT") 
            continue

        if token.pos_ == 'VERB':
            buckets["VERB"].append(lemma)
            continue
            
        if token.pos_ == 'ADJ':
            if token.head.i in noun_map:
                head_noun, bucket_name = noun_map[token.head.i]
                try:
                    noun_index = buckets[bucket_name].index(head_noun)
                    buckets[bucket_name].insert(noun_index + 1, lemma)
                except ValueError:
                     buckets[bucket_name].append(lemma) 
            else:
                buckets["UNCLASSIFIED"].append(lemma) 
            continue
            
        if token.pos_ == 'ADV' and token.lemma_ in ['very', 'too', 'really', 'extremely', 'so']:
            continue 
            
        if token.pos_ == 'ADV':
            buckets["VERB"].append(lemma) 
            continue
            
        if token.pos_ in ['NOUN', 'PROPN', 'INTJ', 'PRON']:
            buckets["UNCLASSIFIED"].append(lemma)
            if token.pos_ in ['NOUN', 'PROPN']:
                 noun_map[token.i] = (lemma, "UNCLASSIFIED")
            continue
    
    # --- 3. Apply Synonym Map to Buckets ---
    for bucket_name in buckets:
        buckets[bucket_name] = [isl_synonym_map.get(word, word) for word in buckets[bucket_name]]
            
    # --- 4. Syntactic Assembly: Build the final gloss in ISL order ---
    final_gloss = []
    final_gloss.extend(buckets["TIME"])
    final_gloss.extend(buckets["PLACE"])
    final_gloss.extend(buckets["SUBJECT"])
    final_gloss.extend(buckets["OBJECT"])
    final_gloss.extend(buckets["UNCLASSIFIED"]) 
    final_gloss.extend(buckets["VERB"])
    final_gloss.extend(buckets["NEGATION"])
    final_gloss.extend(buckets["WH_QUESTION"])

    return final_gloss

# --- API ENDPOINTS ---

# --- MODIFIED: This endpoint ONLY transcribes audio and returns text ---
@app.route('/transcribe', methods=['POST'])
def transcribe_audio():
    """
    API endpoint to handle audio transcription.
    Expects audio file data, returns transcribed text.
    """
    if 'audio_data' not in request.files:
        return jsonify({"error": "No audio file part"}), 400
    
    audio_file = request.files['audio_data']
    
    if audio_file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    try:
        temp_path = os.path.join("temp_audio", "temp_recording.webm")
        audio_file.save(temp_path)

        if not whisper_model:
            return jsonify({"error": "Whisper model not loaded"}), 500
            
        segments, _ = whisper_model.transcribe(temp_path, beam_size=5)
        transcribed_text = "".join(segment.text for segment in segments).strip()
        
        os.remove(temp_path)
        
        # Only return the text, not the gloss
        return jsonify({"transcribed_text": transcribed_text})

    except Exception as e:
        print(f"An error occurred: {e}")
        return jsonify({"error": str(e)}), 500

# --- NEW: This endpoint ONLY translates text and returns gloss ---
@app.route('/translate', methods=['POST'])
def translate_text():
    """
    API endpoint to handle text translation.
    Expects JSON {"text": "..."}, returns ISL gloss array.
    """
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({"error": "No text provided"}), 400
        
    text_to_translate = data['text']
    
    if not text_to_translate:
        return jsonify({"gloss": []})
        
    try:
        # Translate the text to ISL gloss
        isl_gloss = translate_to_isl_gloss(text_to_translate)
        return jsonify({"gloss": isl_gloss})
        
    except Exception as e:
        print(f"An error occurred during translation: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)