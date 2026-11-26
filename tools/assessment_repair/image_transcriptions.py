"""Question wording checked visually against archived CORE form images.

These are document transcriptions, not independent clinical approval.
"""

FORMS = {
    "repetitive-behaviours-questionnaire-3--": {
        "instructions": "Please rate the behaviours you have shown over the last two weeks.",
        "reverse": [],
        "questions": [
            "Like to arrange items in rows or patterns?",
            "Repetitively fiddle with items?",
            "Spin yourself around and around?",
            "Rock backwards and forwards, or side to side, either when sitting or when standing?",
            "Pace or move around repetitively?",
            "Make repetitive hand and/or finger movements?",
            "Have a fascination with specific objects?",
            "Like to look at objects from particular or unusual angles?",
            "Have a special interest in the smell of people or objects?",
            "Have a special interest in the feel of different surfaces?",
            "Have any special objects you like to carry around?",
            "Collect or hoard items of any sort?",
            "Insist on things at home remaining the same?",
            "Get upset about minor changes to objects?",
            "Insist that aspects of daily routine must remain the same?",
            "Insist on doing things in a certain way or re-doing things until they are “just right”?",
            "Play the same music, game or video, or read the same book repeatedly?",
            "Insist on wearing the same clothes or refuse to wear new clothes?",
            "Insist on eating the same foods, or a very small range of foods, at every meal?",
            "What sort of activity will you choose if left to occupy yourself?",
        ],
    },
    "core-10--": {
        "instructions": "This form has 10 statements about how you have been OVER THE LAST WEEK. Please read each statement and think how often you felt that way last week. Then tick the box which is closest to this.",
        "reverse": [2, 3],
        "questions": [
            "I have felt tense, anxious or nervous",
            "I have felt I have someone to turn to for support when needed",
            "I have felt able to cope when things go wrong",
            "Talking to people has felt too much for me",
            "I have felt panic or terror",
            "I made plans to end my life",
            "I have had difficulty getting to sleep or staying asleep",
            "I have felt despairing or helpless",
            "I have felt unhappy",
            "Unwanted images or memories have been distressing me",
        ],
    },
    "core-om--": {
        "instructions": "This form has 34 statements about how you have been OVER THE LAST WEEK. Please read each statement and think how often you felt that way last week. Then tick the box which is closest to this.",
        "reverse": [3, 4, 7, 12, 19, 21, 31, 32],
        "questions": [
            "I have felt terribly alone and isolated",
            "I have felt tense, anxious or nervous",
            "I have felt I have someone to turn to for support when needed",
            "I have felt O.K. about myself",
            "I have felt totally lacking in energy and enthusiasm",
            "I have been physically violent to others",
            "I have felt able to cope when things go wrong",
            "I have been troubled by aches, pains or other physical problems",
            "I have thought of hurting myself",
            "Talking to people has felt too much for me",
            "Tension and anxiety have prevented me doing important things",
            "I have been happy with the things I have done",
            "I have been disturbed by unwanted thoughts and feelings",
            "I have felt like crying",
            "I have felt panic or terror",
            "I made plans to end my life",
            "I have felt overwhelmed by my problems",
            "I have had difficulty getting to sleep or staying asleep",
            "I have felt warmth or affection for someone",
            "My problems have been impossible to put to one side",
            "I have been able to do most things I needed to",
            "I have threatened or intimidated another person",
            "I have felt despairing or hopeless",
            "I have thought it would be better if I were dead",
            "I have felt criticised by other people",
            "I have thought I have no friends",
            "I have felt unhappy",
            "Unwanted images or memories have been distressing me",
            "I have been irritable when with other people",
            "I have thought I am to blame for my problems and difficulties",
            "I have felt optimistic about my future",
            "I have achieved the things I wanted to",
            "I have felt humiliated or shamed by other people",
            "I have hurt myself physically or taken dangerous risks with my health",
        ],
    },
    "yp-core--": {
        "instructions": "These questions are about how you have been feeling – OVER THE LAST WEEK. Please read each question carefully. Think how often you have felt like that in the last week and then put a cross in the box you think fits best.",
        "reverse": [3, 5, 10],
        "questions": [
            "I’ve felt edgy or nervous",
            "I haven’t felt like talking to anyone",
            "I’ve felt able to cope when things go wrong",
            "I’ve thought of hurting myself",
            "There’s been someone I felt able to ask for help",
            "My thoughts and feelings distressed me",
            "My problems have felt too much for me",
            "It’s been hard to go to sleep or stay asleep",
            "I’ve felt unhappy",
            "I’ve done all the things I wanted to",
        ],
    },
}
HASHES = {
    "repetitive-behaviours-questionnaire-3--": "e7820a979b26fbfc823ac106a0187120f0789d8666b3556bc0b080bc79821bce",
    "core-10--": "38f86aa9f8f84dd95e46efbf8a42f91ba60dbf4d4d093b9ed84fba3ba3328b24",
    "core-om--": "af2622879f07dabbf663c61b08a95fde146d58f7a92ef2b37b57870be8165e75",
    "yp-core--": "47d91397772a99b54a45d91d97327d3e8ef350629ebd187754d2a21fdbf2746b",
}


def apply_transcription(key, parsed):
    for token, form in FORMS.items():
        if token not in key:
            continue
        if token in HASHES and parsed["sha256"] != HASHES[token]:
            raise ValueError(
                "Archived image transcription belongs to a different PDF version"
            )
        labels = [
            "Not at all",
            "Only occasionally",
            "Sometimes",
            "Often",
            "Most or all of the time",
        ]
        if token == "core-10--":
            labels[-1] = "Most or all the time"
        parsed["instructions"] = form["instructions"]
        parsed["items"] = []
        for n, text in enumerate(form["questions"], 1):
            reverse = n in form["reverse"]
            page = 2 if token == "core-om--" and n >= 15 else 1
            values = list(reversed(range(5))) if reverse else list(range(5))
            if token.startswith("repetitive-"):
                page = 17 if n <= 14 else 18
                values = list(range(1, 5))
                if n <= 7:
                    labels = [
                        "Never or rarely",
                        "One or more times daily",
                        "15 or more times daily (or at least once an hour)",
                        "30 or more times daily (or at least twice an hour)",
                    ]
                elif n in [13, 16]:
                    labels = [
                        "Never or rarely",
                        "Mild or occasional (does not affect others)",
                        "Marked or notable (occasionally affects others)",
                        "Serious or severe (affects others on a regular basis)",
                    ]
                elif n in [17, 18, 19]:
                    labels = [
                        "Never or rarely",
                        "Mild or occasional (not entirely resistant to change or new things)",
                        "Marked or notable (will tolerate changes when necessary)",
                        "Serious or severe (will not tolerate any changes)",
                    ]
                elif n == 20:
                    labels = [
                        "A range of different and flexible self-chosen activities",
                        "Some varied and flexible interests but commonly chooses the same activities",
                        "Almost always chooses from a restricted range of repetitive activities",
                    ]
                    values = [1, 2, 3]
                else:
                    labels = [
                        "Never or rarely",
                        "Mild or occasional",
                        "Marked or notable",
                        "Serious or extreme",
                    ]
            parsed["items"].append(
                {
                    "source_number": n,
                    "source_label": str(n),
                    "text": text,
                    "page": page,
                    "source_bbox": None,
                    "method": "image_transcription_visually_checked",
                    "review_status": "source_image_checked",
                    "reverse_scored": reverse,
                    "options": [
                        {
                            "label": label,
                            "printed_value": values[i],
                            "score": None,
                            "source_bbox": None,
                        }
                        for i, label in enumerate(labels)
                    ],
                }
            )
        parsed["visual_check"] = (
            "OCR assisted transcription checked against rendered archived form pages on 2026-11-13; no independent clinical review."
        )
    return parsed
