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

# --- ISL Synonym / Vocabulary-Fallback Map ---
# Maps English words with no dedicated sign asset onto the closest available
# sign, so the addressable vocabulary extends past the ~49 hand-authored .glb
# files without needing a new animation for every near-synonym.
#
# IMPORTANT CAVEAT: these mappings are based on common English-language
# synonymy/common-sense judgment, NOT on a verified Indian Sign Language
# source. We tried to confirm sign-sharing against ISLRTC, Talking Hands,
# indiansignlanguage.org, and spreadthesign.com; all were either unreachable,
# blocked, or video-only content that can't be verified without a human
# signer. Treat every entry below as an unverified approximation pending
# review by someone fluent in ISL - a wrong substitution here is actively
# misleading, not just a vocabulary gap. Entries are grouped by target sign
# below; each group was screened for two failure modes before inclusion:
#   1. Cross-POS mismatch - the algorithm buckets a word by its own POS/dependency
#      role BEFORE this map renames it. A synonym with a different typical POS than
#      its target (e.g. mapping an adverb onto a target that's normally an
#      interjection) would carry the *right text* into the *wrong slot* in the
#      final gloss order. Only same-POS clusters are included.
#   2. False-equivalence - common "synonyms" that actually carry a different core
#      meaning in many contexts (e.g. "poor" usually means low-income, not
#      "bad"; "hand"/"pen" are far more often nouns than the verbs
#      "give"/"write") were excluded even though they're loosely related words.
ISL_SYNONYM_MAP = {
    # --- pronouns / greetings (pre-existing, unchanged) ---
    "HOME": "HOUSE", 
    "MINE": "MY", 
    "MYSELF": "I", 
    "ME": "I",
    "HEY": "HELLO", 
    "HI": "HELLO",

    # --- LOOK (verb) ---
    "SEE": "LOOK", 
    "WATCH": "LOOK", 
    "VIEW": "LOOK", 
    "GLANCE": "LOOK", 
    "OBSERVE": "LOOK",

    # --- SPEAK (verb) ---
    "TALK": "SPEAK", 
    "SAY": "SPEAK", 
    "TELL": "SPEAK", 
    "CHAT": "SPEAK", 
    "COMMUNICATE": "SPEAK",

    # --- BIG (adjective, size) ---
    "LARGE": "BIG", 
    "HUGE": "BIG", 
    "GIANT": "BIG", 
    "ENORMOUS": "BIG", 
    "MASSIVE": "BIG",

    # --- SMALL (adjective, size) ---
    "LITTLE": "SMALL", 
    "TINY": "SMALL", 
    "MINI": "SMALL", 
    "MINIATURE": "SMALL",

    # --- GOOD (adjective, quality) ---
    "FINE": "GOOD", 
    "GREAT": "GOOD", 
    "WONDERFUL": "GOOD", 
    "EXCELLENT": "GOOD", 
    "NICE": "GOOD",

    # --- BAD (adjective, quality) --- ("poor" deliberately excluded: usually means low-income)
    "TERRIBLE": "BAD", "AWFUL": "BAD", "HORRIBLE": "BAD",

    # --- HAPPY (adjective, emotion) ---
    "GLAD": "HAPPY", "JOYFUL": "HAPPY", "PLEASED": "HAPPY", "CHEERFUL": "HAPPY", "DELIGHTED": "HAPPY",

    # --- SAD (adjective, emotion) ---
    "UNHAPPY": "SAD", "UPSET": "SAD", "SORROWFUL": "SAD", "GLOOMY": "SAD",

    # --- COME (verb, motion toward) ---
    "ARRIVE": "COME", "APPROACH": "COME",

    # --- GIVE (verb) --- ("hand" excluded: far more often a noun)
    "OFFER": "GIVE", "PROVIDE": "GIVE",

    # --- TAKE (verb) --- ("get"/"hold" excluded: too polysemous / different sense)
    "GRAB": "TAKE", "FETCH": "TAKE",

    # --- STOP (verb) ---
    "HALT": "STOP", "CEASE": "STOP", "QUIT": "STOP",

    # --- EAT (verb) ---
    "CONSUME": "EAT", "DEVOUR": "EAT", "DINE": "EAT",

    # --- WRITE (verb) --- ("pen"/"note" excluded: far more often nouns)
    "JOT": "WRITE", "SCRIBBLE": "WRITE",

    # --- FRIEND (noun) ---
    "BUDDY": "FRIEND", "PAL": "FRIEND", "MATE": "FRIEND", "COMPANION": "FRIEND",

    # --- FAMILY (noun) ---
    "RELATIVES": "FAMILY", "RELATIONS": "FAMILY", "KIN": "FAMILY",

    # --- HOUSE (noun) ---
    "RESIDENCE": "HOUSE", "DWELLING": "HOUSE",

    # --- MAN / WOMAN (noun) --- ("male"/"female" excluded: too often adjectives)
    "GUY": "MAN", "GENTLEMAN": "MAN",
    "LADY": "WOMAN",

    # --- BYE (interjection) ---
    "GOODBYE": "BYE", "FAREWELL": "BYE",

    # --- THANK (verb) --- ("thanks"/"grateful"/"thankful" excluded: different POS - noun/adjective)
    "APPRECIATE": "THANK",

    # --- YES (interjection) --- ("ok"/"okay"/"sure" excluded: can mean "acceptable", not agreement)
    "YEAH": "YES", "YEP": "YES",

    # --- BOOK (noun) --- hypernym fallback: these are all specific *types* of
    # book, substituted with the generic sign rather than dropped entirely.
    "NOVEL": "BOOK", "TEXTBOOK": "BOOK", "NOTEBOOK": "BOOK", "MAGAZINE": "BOOK",
}

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
        "TIME": [], "PLACE": [], "SUBJECT": [], "OBJECT": [], "VERB": [], "MODAL": [],
        "NEGATION": [], "WH_QUESTION": [], "UNCLASSIFIED": []
    }

    # token.i -> bucket name, but only for tokens that got a "head" slot of their own
    # (subjects, objects, verbs, time/place words, modals). Populated in Pass 1 and
    # read back in Pass 2 to attach modifiers to their head regardless of word order.
    token_slot = {}
    # Modifiers deferred to Pass 2: (token, 'before' | 'after') relative to their head.
    modifiers = []

    # --- Pass 1: place every head word first ---
    # Adjectives, compounds, possessives, and coordinated conjuncts all attach to
    # another token (their dependency head). In English (and typically in the
    # gloss for these categories) premodifiers like compounds/possessives/numerals
    # precede their head, so if we tried to attach them in a single left-to-right
    # pass, the head wouldn't have a bucket yet. Splitting into two passes means
    # every possible head is already placed before we resolve any modifier.
    for token in doc:
        lemma = token.lemma_.upper()

        # WH-words must be checked before the determiner skip below: "which" is
        # tagged both WDT and DET, and would otherwise be silently discarded as
        # a plain determiner before ever reaching the WH-question bucket.
        if token.tag_ in ['WDT', 'WP', 'WP$', 'WRB']:
            buckets["WH_QUESTION"].append(lemma)
            continue

        # Negative-polarity words carry inherent negation even with no separate
        # "not"/"n't" token ("no money", "nothing", "nobody"). Only "no" used as
        # a determiner counts here - "no" as a standalone discourse interjection
        # ("no, I don't want it") is a separate response particle, not a negator
        # of its own clause, and would double up with a genuine "don't" elsewhere
        # in the same sentence. Negative pronouns (nobody/nothing/none/neither)
        # still carry their own lexical content, so they aren't skipped - they
        # fall through to normal placement below in addition to marking negation.
        if (token.lemma_ == 'no' and token.pos_ == 'DET') or token.lemma_ in ('nobody', 'nothing', 'none', 'neither'):
            buckets["NEGATION"].append("NOT")
            if token.pos_ == 'DET':
                continue

        # Expletive subjects ("there is...", "it seems...") are grammatical
        # placeholders with no sign-worthy content of their own.
        if token.dep_ == 'expl':
            continue

        if token.pos_ == 'DET' or token.lemma_ == 'be':
            continue

        if token.tag_ == 'MD':
            buckets["MODAL"].append(lemma)
            token_slot[token.i] = "MODAL"
            continue

        if token.pos_ == 'AUX':
            continue

        if token.dep_ == 'neg':
            buckets["NEGATION"].append("NOT")
            continue

        if token.ent_type_ in ['TIME', 'DATE'] or token.lemma_ in ['tomorrow', 'yesterday', 'now', 'today']:
            buckets["TIME"].append(lemma)
            token_slot[token.i] = "TIME"
            continue

        if token.lemma_ == 'home' or token.ent_type_ in ['GPE', 'LOC']:
            buckets["PLACE"].append(lemma)
            token_slot[token.i] = "PLACE"
            continue

        # Adjectives (post-head in ISL) and pre-nominal modifiers (compounds,
        # possessives, numerals) and coordinated conjuncts all resolve in Pass 2.
        if token.pos_ == 'ADJ':
            modifiers.append((token, 'after'))
            continue

        if token.dep_ in ('compound', 'poss', 'nummod'):
            modifiers.append((token, 'before'))
            continue

        # Coordinated verbs ("eat and drink") are a second predicate, not a
        # modifier of whatever noun their head happens to be attached to -
        # route them straight to VERB like any other verb. Only non-verb
        # conjuncts (coordinated nouns/adjectives) get deferred to Pass 2.
        if token.dep_ == 'conj' and token.pos_ != 'VERB':
            modifiers.append((token, 'after'))
            continue

        if 'nsubj' in token.dep_:
            buckets["SUBJECT"].append(lemma)
            token_slot[token.i] = "SUBJECT"
            continue

        # dobj/pobj: direct/prepositional objects. attr: predicate nominative
        # ("she is a doctor"). dative: indirect object ("give me the book").
        # oprd: object predicate ("call me Bob"). All fill the same OBJECT-like slot.
        if token.dep_ in ('dobj', 'pobj', 'attr', 'dative', 'oprd'):
            buckets["OBJECT"].append(lemma)
            token_slot[token.i] = "OBJECT"
            continue

        if token.pos_ == 'VERB':
            buckets["VERB"].append(lemma)
            token_slot[token.i] = "VERB"
            continue

        if token.pos_ == 'ADV' and token.lemma_ in ['very', 'too', 'really', 'extremely', 'so']:
            continue

        if token.pos_ == 'ADV':
            buckets["VERB"].append(lemma)
            continue

        if token.pos_ in ['NOUN', 'PROPN', 'INTJ', 'PRON']:
            buckets["UNCLASSIFIED"].append(lemma)
            token_slot[token.i] = "UNCLASSIFIED"
            continue

    # --- Pass 2: attach modifiers to their (now-placed) head ---
    # A modifier's head can itself be another unresolved modifier (e.g. a possessive
    # on the second half of a coordinated pair: "my brother and my sister" - the
    # second "my" attaches to "sister", which is itself a deferred conjunct). Resolve
    # in dependency order via a worklist instead of raw sentence order, repeating
    # rounds until nothing more can be placed.
    remaining = modifiers
    made_progress = True
    while remaining and made_progress:
        made_progress = False
        still_remaining = []
        for token, placement in remaining:
            head_bucket = token_slot.get(token.head.i)
            if head_bucket is None:
                still_remaining.append((token, placement))
                continue

            lemma = token.lemma_.upper()
            head_lemma = token.head.lemma_.upper()
            try:
                head_index = buckets[head_bucket].index(head_lemma)
                insert_at = head_index + 1 if placement == 'after' else head_index
                buckets[head_bucket].insert(insert_at, lemma)
            except ValueError:
                buckets[head_bucket].append(lemma)
            token_slot[token.i] = head_bucket
            made_progress = True
        remaining = still_remaining

    # Anything left has a head that never got a bucket (e.g. an adjective on a
    # copula that was dropped entirely) - fall back to a plain append.
    for token, placement in remaining:
        lemma = token.lemma_.upper()
        buckets["UNCLASSIFIED"].append(lemma)
        token_slot[token.i] = "UNCLASSIFIED"

    # --- 3. Apply Synonym Map to Buckets ---
    for bucket_name in buckets:
        buckets[bucket_name] = [ISL_SYNONYM_MAP.get(word, word) for word in buckets[bucket_name]]

    # --- 4. Syntactic Assembly: Build the final gloss in ISL order ---
    final_gloss = []
    final_gloss.extend(buckets["TIME"])
    final_gloss.extend(buckets["PLACE"])
    final_gloss.extend(buckets["SUBJECT"])
    final_gloss.extend(buckets["OBJECT"])
    final_gloss.extend(buckets["UNCLASSIFIED"])
    final_gloss.extend(buckets["VERB"])
    final_gloss.extend(buckets["MODAL"])
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