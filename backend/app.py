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
    
# --- NEW: AI-Guided Reordering Engine (Implements ISL Grammar Rules) ---
def translate_to_isl_gloss(text: str) -> list:
    """
    Translates an English sentence into a grammatically-ordered ISL gloss sequence
    using a "bucket" sorting method based on spaCy's linguistic analysis.
    This version is designed to be robust and scalable, avoiding non-general rules.
    """
    if not nlp:
        return ["Error: nlp model not loaded"]
        
    doc = nlp(text.strip().lower())
    
    # 1. Initialize ISL Grammatical Buckets
    buckets = {
        "TIME": [],
        "PLACE": [],
        "SUBJECT": [],
        "OBJECT": [],
        "VERB": [],
        "NEGATION": [],
        "WH_QUESTION": [],
        "UNCLASSIFIED": [] # Fallback for important words we can't classify
    }
    
    # This dictionary maps English lemmas to a primary ISL sign concept.
    # This is a scalable way to handle linguistic exceptions.
    isl_synonym_map = {
        "FOOD": "EAT",
        "HOME": "HOUSE",
        "MINE": "MY",
        "MYSELF": "I",
        "ME": "I",
        "HEY": "HELLO",
        "HI": "HELLO",
        "SEE": "LOOK"
    }

    # This maps a token's *position* to its noun lemma, so we can attach adjectives
    noun_map = {}

    # --- 2. Linguistic Triage: Sort tokens into buckets (General Rules) ---
    for token in doc:
        lemma = token.lemma_.upper()

        # Rules 1, 2, 3, 6: Skip articles, 'be' verbs, and auxiliary verbs
        if token.pos_ == 'DET' or token.lemma_ == 'be' or token.pos_ == 'AUX':
            continue
            
        # Rule 11: Handle Negation
        if token.dep_ == 'neg' or token.text == 'dont':
            buckets["NEGATION"].append("NOT")
            continue
            
        # Rule 12: Handle WH-Questions
        if token.tag_ in ['WDT', 'WP', 'WP$', 'WRB']: # 'what', 'who', 'where', 'why'
            buckets["WH_QUESTION"].append(lemma)
            continue
            
        # Rule 8: Handle Time
        if token.ent_type_ == 'TIME' or token.lemma_ in ['tomorrow', 'yesterday', 'now', 'today']:
            buckets["TIME"].append(lemma)
            continue
            
        # Rule 8 & 5: Handle Place
        if token.lemma_ == 'home' or token.ent_type_ in ['GPE', 'LOC']:
            buckets["PLACE"].append(lemma)
            continue
            
        # Rule 4: Handle Subject
        if 'nsubj' in token.dep_:
            buckets["SUBJECT"].append(lemma)
            noun_map[token.i] = lemma # Track this noun's position
            continue
            
        # Rule 4 & 5: Handle Object (direct or from preposition)
        if 'dobj' in token.dep_ or 'pobj' in token.dep_:
            buckets["OBJECT"].append(lemma)
            noun_map[token.i] = lemma # Track this noun's position
            continue

        # Rule 7 & 14: Handle Verbs
        if token.pos_ == 'VERB':
            buckets["VERB"].append(lemma)
            continue
            
        # Rule 10: Handle Adjectives
        if token.pos_ == 'ADJ':
            # Check if this adjective's "head" (the word it modifies) is a noun we've already tracked
            if token.head.i in noun_map:
                head_noun = noun_map[token.head.i]
                # Find which bucket the noun is in and append the adjective *after* it
                if head_noun in buckets["SUBJECT"]:
                    buckets["SUBJECT"].append(lemma)
                elif head_noun in buckets["OBJECT"]:
                    buckets["OBJECT"].append(lemma)
            else:
                buckets["UNCLASSIFIED"].append(lemma) # Can't find its noun, but it's important
            continue
            
        # Rule 13: Handle & remove emphasis adverbs
        if token.pos_ == 'ADV' and token.lemma_ in ['very', 'too', 'really', 'extremely', 'so']:
            continue # Explicitly skip them as per ISL rules
            
        # Handle other important adverbs (e.g., of manner like 'quickly')
        # We place them *with* the verb.
        if token.pos_ == 'ADV':
            buckets["VERB"].append(lemma)
            continue
            
        # Handle other important content (Pronouns, Nouns, Interjections)
        if token.pos_ in ['NOUN', 'PROPN', 'INTJ', 'PRON']:
            buckets["UNCLASSIFIED"].append(lemma)
    
    # --- 2.5: Apply Synonym Map to Buckets ---
    # This is a scalable mapping operation.
    for bucket_name in buckets:
        buckets[bucket_name] = [isl_synonym_map.get(word, word) for word in buckets[bucket_name]]

    # --- 2.6: REMOVED: The specific "EAT" redundancy check was unscalable.
            
    # --- 3. Syntactic Assembly: Build the final gloss in ISL order ---
    # This is a general rule.
    final_gloss = []
    final_gloss.extend(buckets["TIME"])
    final_gloss.extend(buckets["PLACE"])
    final_gloss.extend(buckets["SUBJECT"])
    final_gloss.extend(buckets["OBJECT"])
    final_gloss.extend(buckets["UNCLASSIFIED"]) # Add any leftover important words
    final_gloss.extend(buckets["VERB"])
    final_gloss.extend(buckets["NEGATION"])
    final_gloss.extend(buckets["WH_QUESTION"])

    # --- 4. REMOVED: Final duplicate cleanup was an incorrect assumption. ---
    # The assembled list is the most honest output of the engine.

    return final_gloss

# --- API ENDPOINTS (No changes needed below) ---
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

