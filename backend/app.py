import spacy

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
                # dobj is the direct object
                if child.dep_ == "dobj":
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


# --- This block allows us to test the translator directly ---
if __name__ == '__main__':
    print("-" * 30)
    print("Translator Test Block")
    print("-" * 30)
    
    test_sentence_1 = "The boy is eating an apple"
    test_sentence_2 = "I love programming"
    test_sentence_3 = "She reads a book"

    gloss_1 = translate_to_isl_gloss(test_sentence_1)
    gloss_2 = translate_to_isl_gloss(test_sentence_2)
    gloss_3 = translate_to_isl_gloss(test_sentence_3)
    
    print(f"English: '{test_sentence_1}'")
    print(f"ISL Gloss: {gloss_1}")
    print("-" * 30)

    print(f"English: '{test_sentence_2}'")
    print(f"ISL Gloss: {gloss_2}")
    print("-" * 30)
    
    print(f"English: '{test_sentence_3}'")
    print(f"ISL Gloss: {gloss_3}")
    print("-" * 30)
