"""ASHA milestone -> communication-domain map.

Each key is a (band_key, index) pair where band_key is the age band in months
and index is the milestone's position in that band's list inside
checklist_options.json. Indexes are positional: reordering or editing that
file invalidates this map, so the two must be changed together.

Every milestone is assigned exactly one domain. Milestones that genuinely
straddle two domains are assigned their dominant domain here and listed in
AMBIGUOUS below with the reasoning.

NOTE: reviewed by <clinician> on <date> — pending sign-off.
"""

EXPRESSIVE = "Expressive Language"
RECEPTIVE = "Receptive Language"
SOCIAL = "Social Communication"

MILESTONE_DOMAINS = {
    # --- 3 months ---
    (3, 0): RECEPTIVE,   # Alerts to sound.
    (3, 1): SOCIAL,      # Quiets or smiles when you talk.
    (3, 2): SOCIAL,      # Makes sounds back and forth with you.
    (3, 3): EXPRESSIVE,  # Makes sounds that differ depending on wh
    (3, 4): EXPRESSIVE,  # Coos, makes sounds like ooooo, aahh, and
    (3, 5): RECEPTIVE,   # Recognizes loved ones and some common ob
    (3, 6): RECEPTIVE,   # Turns or looks toward voices or people t

    # --- 6 months ---
    (6, 0): SOCIAL,      # Giggles and laughs.
    (6, 1): SOCIAL,      # Responds to facial expressions.
    (6, 2): RECEPTIVE,   # Looks at objects of interest and follows
    (6, 3): RECEPTIVE,   # Reacts to toys that make sounds, like th
    (6, 4): EXPRESSIVE,  # Vocalizes during play or with objects in
    (6, 5): EXPRESSIVE,  # Vocalizes different vowel sounds-sometim
    (6, 6): EXPRESSIVE,  # Blows 'raspberries.'

    # --- 9 months ---
    (9, 0): RECEPTIVE,   # Looks at you when you call their name.
    (9, 1): RECEPTIVE,   # Stops for a moment when you say, 'No.'
    (9, 2): EXPRESSIVE,  # Babbles long strings of sounds, like mam
    (9, 3): SOCIAL,      # Looks for loved ones when upset.
    (9, 4): SOCIAL,      # Raises arms to be picked up.
    (9, 5): RECEPTIVE,   # Recognizes the names of some people and
    (9, 6): SOCIAL,      # Pushes away unwanted objects.

    # --- 12 months ---
    (12, 0): SOCIAL,      # By age 10 months, reaches for objects.
    (12, 1): SOCIAL,      # Points, waves, and shows or gives object
    (12, 2): SOCIAL,      # Imitates and initiates gestures for enga
    (12, 3): EXPRESSIVE,  # Tries to copy sounds that you make.
    (12, 4): RECEPTIVE,   # Enjoys dancing.
    (12, 5): RECEPTIVE,   # Responds to simple words and phrases lik
    (12, 6): EXPRESSIVE,  # Says one or two words-like mama, dada, h

    # --- 18 months ---
    (18, 0): RECEPTIVE,   # Looks around when asked 'where' question
    (18, 1): RECEPTIVE,   # Follows directions-like 'Give me the bal
    (18, 2): SOCIAL,      # Points to make requests, to comment, or
    (18, 3): EXPRESSIVE,  # shakes head for 'no' and nods head for '
    (18, 4): EXPRESSIVE,  # Understands and uses words for common ob
    (18, 5): RECEPTIVE,   # Identifies one or more body parts.
    (18, 6): SOCIAL,      # Uses gestures when excited, like clappin
    (18, 7): EXPRESSIVE,  # Uses a combination of long strings of so

    # --- 24 months ---
    (24, 0): EXPRESSIVE,  # Uses and understands at least 50 differe
    (24, 1): EXPRESSIVE,  # Puts two or more words together-like mor
    (24, 2): RECEPTIVE,   # Follows two-step directions-like 'Get th
    (24, 3): EXPRESSIVE,  # Uses words like me, mine, and you.
    (24, 4): EXPRESSIVE,  # Uses words to ask for help.
    (24, 5): EXPRESSIVE,  # Uses possessives, like Daddy's sock.

    # --- 36 months (3 years) ---
    (36, 0): EXPRESSIVE,   # Uses word combinations often but may occ
    (36, 1): SOCIAL,       # Tries to get your attention by saying, L
    (36, 2): EXPRESSIVE,   # Says their name when asked.
    (36, 3): EXPRESSIVE,   # Uses some plural words like birds or toy
    (36, 4): EXPRESSIVE,   # Uses -ing verbs like eating or running.
    (36, 5): EXPRESSIVE,   # Gives reasons for things and events, lik
    (36, 6): EXPRESSIVE,   # Asks why and how.
    (36, 7): RECEPTIVE,    # Answers questions like 'What do you do w
    (36, 8): EXPRESSIVE,   # Correctly produces p, b, m, h, w, d, and
    (36, 9): EXPRESSIVE,   # Correctly produces most vowels in words.
    (36, 10): EXPRESSIVE,  # Speech is becoming clearer but may not b

    # --- 48 months (4 years) ---
    (48, 0): EXPRESSIVE,   # Compares things, with words like bigger
    (48, 1): EXPRESSIVE,   # Tells you a story from a book or a video
    (48, 2): RECEPTIVE,    # Understands and uses more location words
    (48, 3): EXPRESSIVE,   # Uses words like a or the when talking, l
    (48, 4): RECEPTIVE,    # Pretends to read alone or with others.
    (48, 5): RECEPTIVE,    # Recognizes signs and logos like STOP.
    (48, 6): EXPRESSIVE,   # Pretends to write or spell and can write
    (48, 7): EXPRESSIVE,   # Correctly produces t, k, g, f, y, and -i
    (48, 8): EXPRESSIVE,   # Says all the syllables in a word.
    (48, 9): EXPRESSIVE,   # Says the sounds at the beginning, middle
    (48, 10): EXPRESSIVE,  # By age 4 years, your child talks smoothl
    (48, 11): EXPRESSIVE,  # By age 4 years, your child speaks so tha
    (48, 12): EXPRESSIVE,  # By age 4 years, your child says all soun

    # --- 60 months (5 years) ---
    (60, 0): EXPRESSIVE,   # Produces grammatically correct sentences
    (60, 1): EXPRESSIVE,   # Includes (1) main characters, settings,
    (60, 2): EXPRESSIVE,   # Uses at least one irregular plural form,
    (60, 3): RECEPTIVE,    # Understands and uses location words, lik
    (60, 4): EXPRESSIVE,   # Uses more words for time-like yesterday
    (60, 5): RECEPTIVE,    # Follows simple directions and rules to p
    (60, 6): RECEPTIVE,    # Locates the front of a book and its titl
    (60, 7): EXPRESSIVE,   # Recognizes and names 10 or more letters
    (60, 8): RECEPTIVE,    # Imitates reading and writing from left t
    (60, 9): RECEPTIVE,    # Blends word parts, like cup + cake = cup
    (60, 10): EXPRESSIVE,  # Produces most consonants correctly, and
}

# Milestones that straddle domains: dominant domain assigned above, reasoning here.
AMBIGUOUS = [
    ((3, 1), "Quieting to voice is auditory-receptive, but the observable behavior is a social response to a partner; band 3 idx 0 already covers pure sound alerting."),
    ((3, 2), "Vocalizing is expressive output, but the milestone targets the back-and-forth contingency, i.e. proto-conversational turn-taking."),
    ((6, 1), "Processing facial affect is input processing, but it is nonverbal social-signal reading rather than language comprehension."),
    ((6, 2), "Visual tracking is attention to input rather than communicative interaction; scored Receptive because it is non-dyadic."),
    ((9, 4), "Arms-up is a gesture, but it functions as a request directed at a partner, so Social per the gesture rule."),
    ((9, 6), "Could be read as pure motor behavior; scored Social because it is a nonverbal act of rejection addressed to a partner."),
    ((12, 0), "Reaching is motoric, but at 10 months it functions as a proto-imperative request gesture toward a partner."),
    ((12, 1), "Pointing/showing/giving are gestures used to share and request, not word substitutes, so Social rather than Expressive."),
    ((12, 3), "Vocal imitation has a social-reciprocity component, but the measured skill is sound production."),
    ((12, 4), "Scored Receptive as a response to music/auditory input; the shared-enjoyment element is social."),
    ((18, 2), "Same call as (12,1): pointing to request/comment/inform is a social-pragmatic gesture, not a lexical substitute."),
    ((18, 3), "Gesture, but head shake/nod substitutes for the words 'no'/'yes', so Expressive per the gesture rule."),
    ((18, 4), "Item states 'understands and uses'; scored Expressive to match (24,0) so vocabulary is one consistent domain."),
    ((24, 0), "Item states 'uses and understands'; expressive vocabulary size plus the speech-clarity clause dominate."),
    ((24, 4), "Requesting is a pragmatic function, but the definition scopes Social requesting to gestures; requesting via words is Expressive."),
    ((36, 1), "Uses words, but the skill measured is initiating joint attention, which is explicitly Social."),
    ((36, 7), "Response is verbal, but the target skill is comprehension of wh-questions; ASHA files 'answers questions' under Hearing and Understanding."),
    ((48, 2), "States 'understands and uses'; location words are named explicitly under Receptive, so scored Receptive and matched to (60,3)."),
    ((48, 4), "Pretend reading is symbolic play, but scored Receptive with the other emergent-literacy/print-concept items."),
    ((48, 5), "Logo reading is not decoding, but print/logo recognition is explicitly Receptive."),
    ((60, 3), "Same call as (48,2): 'understands and uses' location words scored Receptive for cross-band consistency."),
    ((60, 5), "Game rules carry a social component, but following directions is Receptive in every band per the consistency rule."),
    ((60, 7), "Recognizing letters is receptive print knowledge, but naming letters and writing one's name are productive, and 2 of 3 clauses are output."),
    ((60, 8), "Mentions writing, but the skill is print directionality knowledge, grouped with (48,4) and (60,6)."),
    ((60, 9), "Blending requires producing the fused word; scored Receptive because phonological awareness is auditory analysis and 'identifies rhyming words' is a recognition judgment."),
]
