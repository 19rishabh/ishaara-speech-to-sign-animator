import spacy
from flask import Flask, request, jsonify
from flask_cors import CORS

# Initialize Flask app
app = Flask(__name__)
# Enable CORS to allow browser to communicate with the server
CORS(app)

# Load the small English model for spaCy
# This model is loaded once when the application starts
try:
    nlp = spacy.load("en_core_web_sm")
    print("spaCy model loaded successfully.")
except OSError:
    print("spaCy model not found. Please run 'python -m spacy download en_core_web_sm'")
    nlp = None

def translate_to_isl_gloss(text: str) -> list:
    """
    Translates a simple English sentence into an ISL gloss sequence.
    This is a simplified rule-based approach for demonstration.
    ISL generally follows a Subject-Object-Verb (SOV) structure.
    
    Args:
        text: The input English sentence.

    Returns:
        A list of strings representing the ISL gloss.
    """
    if not nlp:
        return ["Error: spaCy model not loaded."]
        
    doc = nlp(text.strip().lower())
    
    subject = ""
    direct_object = ""
    root_verb = ""

    # Find the root verb and its direct dependencies
    for token in doc:
        if token.dep_ == "ROOT":
            root_verb = token.lemma_  # Use lemma for the base form of the verb
            for child in token.children:
                # nsubj is the nominal subject
                if child.dep_ == "nsubj":
                    subject = child.text
                # dobj is the direct object, intj is an interjection
                if child.dep_ in ("dobj", "intj"):
                    direct_object = child.text

    # Basic check to handle sentences that don't fit the simple S-O-V pattern
    if not root_verb:
        return [word.text.upper() for word in doc] # Fallback to word-by-word

    # Construct the gloss in SOV order, filtering out empty strings
    gloss = [
        subject.upper(),
        direct_object.upper(),
        root_verb.upper()
    ]
    
    return [word for word in gloss if word]

@app.route('/translate', methods=['POST'])
def translate():
    """
    API endpoint to handle translation requests.
    Expects a JSON payload with a "text" key.
    """
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({"error": "Invalid request. 'text' key is required."}), 400
    
    english_text = data['text']
    isl_gloss = translate_to_isl_gloss(english_text)
    
    return jsonify({"gloss": isl_gloss})


# --- To run this Flask server ---
# 1. Make sure your venv is active.
# 2. In your terminal, run the command: flask run
# 3. The server will start, typically on http://127.0.0.1:5000
if __name__ == '__main__':
    # This allows you to run the app with `python app.py` as well
    app.run(debug=True)

