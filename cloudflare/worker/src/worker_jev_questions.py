"""Versioned, independent Noul questions for the bounded event catalog."""

TAXONOMY_VERSION = "event-types-v1"
QUESTION_VERSION = "event-type-questions-v1"

# Mirrored in shared/jev-questions.json for review, with parity enforced by tests.
# Category names alone are not sent to the model; each instruction is explicit.
QUESTION_DEFINITIONS = {
    "local_festivals_spectacle": (
        "Is a local festival or public spectacle a primary activity of this event?",
        (
            "A parade, fireworks display, festive street monument, procession, or "
            "flower battle is a primary advertised activity."
        ),
        "Local festivals and public spectacles are absent or only incidental context.",
    ),
    "hands_on_learning": (
        (
            "Is hands-on learning or an interactive educational experience a "
            "primary activity of this event?"
        ),
        (
            "A science museum activity, interactive exhibit, children's workshop, "
            "aquarium show, planetarium show, or educational large-format film is a "
            "primary advertised activity."
        ),
        (
            "Hands-on or interactive educational experiences are absent or only "
            "incidental."
        ),
    ),
    "animals_and_nature": (
        "Is experiencing animals or nature a primary activity of this event?",
        (
            "An animal park visit, keeper talk, nature boat trip, wetland visit, "
            "birdwatching, or sunset nature outing is a primary advertised "
            "activity."
        ),
        (
            "Animals and nature are absent or merely the setting for an unrelated "
            "activity."
        ),
    ),
    "parks_and_play": (
        "Is outdoor play or recreation in a park a primary activity of this event?",
        (
            "A destination playground visit, park recreation event, picnic, or "
            "bike-friendly leisure outing is a primary advertised activity."
        ),
        (
            "Park recreation and outdoor play are absent or merely the setting for "
            "an unrelated activity."
        ),
    ),
    "kid-friendly_culture": (
        (
            "Is an accessible cultural activity for families with children a "
            "primary activity of this event?"
        ),
        (
            "A craft market, family theatre or puppetry, child-accessible street "
            "performance, or museum family day is a primary advertised activity."
        ),
        (
            "Family-accessible cultural activities are absent, adult-only, or "
            "merely incidental."
        ),
    ),
    "live_music": (
        "Is a live musical performance or DJ set a primary activity of this event?",
        (
            "A concert, live band, jazz or classical performance, recital, or DJ "
            "set is a primary advertised activity."
        ),
        (
            "Live music and DJ sets are absent or only incidental background "
            "entertainment."
        ),
    ),
    "performing_arts": (
        "Is a performing arts show a primary activity of this event?",
        (
            "Theatre, dance performance, opera, comedy, or circus is a primary "
            "advertised activity."
        ),
        "Performing arts shows are absent or only incidental entertainment.",
    ),
    "art_exhibitions": (
        (
            "Is an art, photography, design, or museum exhibition a primary "
            "activity of this event?"
        ),
        (
            "An exhibition or gallery opening presenting art, photography, design, "
            "or museum collections is a primary advertised activity."
        ),
        "Exhibitions are absent or merely incidental decoration or context.",
    ),
    "film": (
        "Is a film screening or film festival a primary activity of this event?",
        (
            "A cinema screening, open-air cinema, film festival, or documentary "
            "screening is a primary advertised activity."
        ),
        "Film screenings are absent or only incidental background video.",
    ),
    "food_drink": (
        "Is a food or drink experience a primary activity of this event?",
        (
            "A food festival, food market, tasting, or cooking class is a primary "
            "advertised activity."
        ),
        "Food and drink are absent or only incidental refreshments.",
    ),
    "sports_active": (
        "Is sport or an active physical outing a primary activity of this event?",
        (
            "A sports match, running or cycling event, group fitness session, or "
            "guided hike is a primary advertised activity."
        ),
        "Sport and active physical outings are absent or only incidental movement.",
    ),
    "tours_heritage": (
        "Is a guided tour or heritage experience a primary activity of this event?",
        (
            "A guided city walk, heritage tour, historic-site visit, or "
            "architecture tour is a primary advertised activity."
        ),
        (
            "Tours and heritage experiences are absent or merely the setting for an "
            "unrelated activity."
        ),
    ),
}
