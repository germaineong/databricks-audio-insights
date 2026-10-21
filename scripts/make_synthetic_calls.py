"""Generate synthetic two-speaker contact-centre calls for the audio insights demo, using macOS `say` and ffmpeg.

Each call is a scripted dialogue between an Acme Telecom agent and a customer, voiced with two different macOS voices,
joined with short pauses and encoded as mono 16 kHz MP3: samples/calls/ holds the calls to upload and samples/spare/
the spares kept back for a live "new file arrives" run. File names are neutral on purpose, so the call type has to come
from the transcript; samples/manifest.json maps each file to its scenario and the call_insights values the pipeline
should produce. All companies, names and numbers are fictional.

Usage: python3 make_synthetic_calls.py
"""
import json
import pathlib
import random
import subprocess
import tempfile
import wave

ROOT = pathlib.Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
SAMPLE_RATE = 16000

# A turn is (role, text) or (role, text, pause_seconds_after); otherwise the pause is a random 0.35-0.9 s.
CALLS = [
    {
        "file": "call-20261020-0912.mp3",
        "scenario": "Billing dispute, resolved. Agent callback, so the customer speaks first.",
        "upload": True,
        "voices": {"agent": "Samantha", "customer": "Daniel"},
        "expected": {"call_reason": "billing", "resolution_status": "resolved", "agent_speaker_id": "2"},
        "turns": [
            ("customer", "Hello, Marcus Lee speaking. Who's calling, please?"),
            ("agent", "Hi Marcus, this is Priya from Acme Telecom billing. I'm returning your call from this morning "
                      "about your October bill. Is now a good time?"),
            ("customer", "Yes, thanks for calling back. Honestly, I'm pretty annoyed. My bill this month is a hundred "
                         "and nineteen dollars eighty, when it's normally fifty-nine ninety. It looks like I've been "
                         "charged twice."),
            ("agent", "I'm sorry about that, I can understand why that's frustrating. Before I look into it, can you "
                      "confirm the last four digits of your account number?"),
            ("customer", "Sure, it's four, four, one, seven."),
            ("agent", "Thank you. Okay, I can see the bill now. You switched from Fibre Five Hundred to Fibre One Gig "
                      "on the third of October, is that right?"),
            ("customer", "That's right. Your sales team told me it would only cost five dollars more a month."),
            ("agent", "And that part is correct. What happened is that your old plan wasn't closed when the new one "
                      "started, so both plans were billed for the full month. That was our mistake, not yours."),
            ("customer", "So what happens now? I really don't want to keep paying for two plans."),
            ("agent", "I've just closed the old plan, and I'm issuing a refund of fifty-nine dollars ninety for the "
                      "duplicate charge. I'm also adding a ten dollar credit to your next bill for the trouble."),
            ("customer", "Okay. That's actually a lot better than I expected. When will I see the refund?"),
            ("agent", "It goes back to the card on file within three to five business days. I've also emailed you a "
                      "confirmation with the reference number B, R, seven, two, zero, four."),
            ("customer", "Great. And next month I'll only be billed for the new plan?"),
            ("agent", "Exactly. Sixty-four ninety, minus the ten dollar credit, so fifty-four ninety for November."),
            ("customer", "Perfect. Thanks, Priya, I really appreciate you sorting this out so quickly."),
            ("agent", "You're very welcome, Marcus. Is there anything else I can help you with today?"),
            ("customer", "No, that's everything. Have a good day."),
            ("agent", "You too. Thank you for being with Acme Telecom. Goodbye."),
        ],
    },
    {
        "file": "call-20261020-1047.mp3",
        "scenario": "Fibre outage, escalated to network operations with a technician visit and a service credit.",
        "upload": True,
        "voices": {"agent": "Rishi", "customer": "Karen"},
        "expected": {"call_reason": "technical_issue", "resolution_status": "escalated", "agent_speaker_id": "1"},
        "turns": [
            ("agent", "Thank you for calling Acme Telecom technical support, my name is Arjun. How can I help you "
                      "today?"),
            ("customer", "Hi Arjun. My internet has been down since Saturday morning. That's three days now, and I "
                         "work from home, so this is a really big problem for me."),
            ("agent", "I'm very sorry to hear that. Let me pull up your account. Can I have your full name and the "
                      "service address, please?"),
            ("customer", "Sarah Tan, block two one four, Tampines Street twenty one."),
            ("agent", "Thank you, Sarah. I can see your fibre connection. What lights are showing on your router "
                      "right now?"),
            ("customer", "The power light is green, but the one labelled P, O, N is blinking red. I've already "
                         "restarted it about five times."),
            ("agent", "Thank you for trying that. Let me run a line test from our side. It takes about thirty "
                      "seconds.", 2.5),
            ("agent", "Alright, the test shows no signal reaching your fibre terminal at all. So it isn't your "
                      "router. The problem is on our network."),
            ("customer", "Then why hasn't anybody fixed it? I called on Saturday and they told me it would be back in "
                         "a few hours."),
            ("agent", "I understand, and I apologise that you were given the wrong information. There was a fault at "
                      "the Tampines exchange affecting several buildings, and your line didn't come back with the "
                      "others. I can't fix it remotely, so I'm escalating it to our network operations team as a "
                      "priority case."),
            ("customer", "Escalating it means what, exactly? Another few days of waiting?"),
            ("agent", "No. I've booked a technician to visit your building tomorrow, between nine and twelve in the "
                      "morning, and your case is marked as priority. Your escalation reference is N, O, C, four, "
                      "eight, one, five, two."),
            ("customer", "Tomorrow morning. Fine. And what about the three days I've had no service? I've been paying "
                         "for this."),
            ("agent", "That's fair. I've applied a service credit for the full outage, and I'm sending you a free "
                      "fifty gigabyte mobile data pass today, so you can hotspot from your phone until the line is "
                      "fixed."),
            ("customer", "Okay, the data pass helps. But if the technician doesn't turn up tomorrow, I'm going to "
                         "cancel."),
            ("agent", "I completely understand. I'll personally call you tomorrow afternoon to confirm the repair is "
                      "done. Is this the best number to reach you on?"),
            ("customer", "Yes, this number is fine."),
            ("agent", "Great. So to recap: a technician tomorrow between nine and twelve, reference N, O, C, four, "
                      "eight, one, five, two, a full credit for the outage, and a fifty gigabyte data pass by text "
                      "message today. Is there anything else I can help with?"),
            ("customer", "No. Just please make sure it actually gets fixed this time."),
            ("agent", "I will. Thank you for your patience, Sarah, and again, I'm sorry for the trouble."),
        ],
    },
    {
        "file": "call-20261020-1405.mp3",
        "scenario": "Cancellation after repeated outages and price rises; retention offer declined, cancellation booked.",
        "upload": True,
        "voices": {"agent": "Moira", "customer": "Aman"},
        "expected": {"call_reason": "cancellation", "resolution_status": "resolved", "agent_speaker_id": "1"},
        "turns": [
            ("agent", "Good afternoon, you've reached Acme Telecom customer care, this is Emma speaking. How can I "
                      "help?"),
            ("customer", "Hi Emma. I'd like to cancel my home broadband, please."),
            ("agent", "I'm sorry to hear that, but I can certainly help. Could I have your name and account number, "
                      "please?"),
            ("customer", "Ravi Kumar. The account number is six, two, nine, zero, three, eight."),
            ("agent", "Thank you, Ravi. I can see you've been with us for just over four years. May I ask why you're "
                      "looking to cancel?"),
            ("customer", "Two reasons, really. The outage in Tampines this weekend was the third one since August, and "
                         "my bill keeps going up. I'm paying sixty-nine ninety now for the same plan that used to be "
                         "forty-nine ninety."),
            ("agent", "I understand, and I'm sorry about the outages. That's not the experience we want you to have. "
                      "Before you decide, I can offer you twenty percent off your plan for the next twelve months, "
                      "which would bring it down to fifty-five ninety."),
            ("customer", "I appreciate that, but I've already signed up with another provider. They're installing on "
                         "Friday."),
            ("agent", "Understood. Is there anything that would change your mind? I could also add a free speed "
                      "upgrade to one gigabit."),
            ("customer", "No, thank you. My mind is made up."),
            ("agent", "No problem at all. I'll go ahead and process the cancellation now. Your service stays active "
                      "until the end of your billing cycle on the thirty-first of October, so you won't have a gap "
                      "before your new provider installs."),
            ("customer", "That works. Is there an early termination fee?"),
            ("agent", "No, your contract ended last year, so there's no termination fee. You'll just need to return "
                      "the router. I'll email you a prepaid return label, and you can drop it off at any post office "
                      "within fourteen days."),
            ("customer", "Okay. And what about the final bill?"),
            ("agent", "Your final bill will be prorated to the thirty-first and emailed to you in early November. Your "
                      "cancellation reference is C, X, three, three, zero, nine."),
            ("customer", "Great. Thanks for making it easy."),
            ("agent", "You're welcome, Ravi. I'm sorry to see you go, and if you ever want to come back, just give us "
                      "a call. Have a lovely afternoon."),
            ("customer", "You too, take care. Bye."),
        ],
    },
    {
        "file": "call-20261020-1530.mp3",
        "scenario": "Spare for the live upload: happy customer upgrades to a family bundle (sales, resolved).",
        "upload": False,
        "voices": {"agent": "Tessa", "customer": "Rishi"},
        "expected": {"call_reason": "sales", "resolution_status": "resolved", "agent_speaker_id": "1"},
        "turns": [
            ("agent", "Hello, and thank you for calling Acme Telecom sales. This is Nadia. How can I help you today?"),
            ("customer", "Hi Nadia. I'm an existing customer, and I'd like to add two mobile lines for my kids. I "
                         "might upgrade my home fibre as well."),
            ("agent", "Wonderful, I can help with both. Can I have your name and account number?"),
            ("customer", "Sure. Kevin Ong, account seven, seven, one, two, zero, five."),
            ("agent", "Thanks, Kevin. You're on Fibre Five Hundred at the moment. Because you're adding mobile lines, "
                      "you qualify for our family bundle. That's Fibre One Gig plus three mobile lines with twenty "
                      "gigabytes each, for ninety-nine dollars a month."),
            ("customer", "And what am I paying now?"),
            ("agent", "Your fibre is fifty-nine ninety and your own mobile plan is thirty-five, so ninety-four ninety "
                      "in total. For five dollars more, you get double the speed and two extra lines."),
            ("customer", "That's a really good deal. Do the kids' lines come with parental controls?"),
            ("agent", "They do. You can set screen time limits and content filters in the Acme app, at no extra "
                      "cost."),
            ("customer", "Great. Let's do it."),
            ("agent", "Lovely. I've set up the bundle from your next billing cycle on the first of November. The two "
                      "SIM cards will be couriered to you within two working days, and the speed upgrade happens "
                      "automatically tonight, so no technician is needed."),
            ("customer", "Excellent. That was easy."),
            ("agent", "You'll get an email confirmation in a few minutes with the order number S, O, nine, one, four, "
                      "six. Is there anything else I can help with?"),
            ("customer", "No, that's all. Thank you, Nadia, you've been really helpful."),
            ("agent", "My pleasure, Kevin. Enjoy the faster internet, and have a great day."),
        ],
    },
]


def sample_path(call):
    """Where a call's MP3 lives: samples/calls/ if it is meant to be uploaded, samples/spare/ otherwise."""
    return SAMPLES / ("calls" if call["upload"] else "spare") / call["file"]


def speak(voice, text, path):
    """Render one turn to a mono 16-bit WAV at SAMPLE_RATE with macOS `say`."""
    subprocess.run(["say", "-v", voice, "--file-format=WAVE", f"--data-format=LEI16@{SAMPLE_RATE}", "-o", str(path),
                    text], check=True)


def build(call, workdir):
    """Voice every turn, join the turns with pauses and encode the call as MP3 at sample_path(call). Returns that path."""
    rng = random.Random(call["file"])
    frames = [bytes(2 * int(SAMPLE_RATE * 0.4))]
    for i, (role, text, *pause) in enumerate(call["turns"]):
        turn_wav = workdir / f"turn{i:02d}.wav"
        speak(call["voices"][role], text, turn_wav)
        with wave.open(str(turn_wav)) as w:
            frames.append(w.readframes(w.getnframes()))
        frames.append(bytes(2 * int(SAMPLE_RATE * (pause[0] if pause else rng.uniform(0.35, 0.9)))))
    call_wav = workdir / "call.wav"
    with wave.open(str(call_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(b"".join(frames))
    mp3 = sample_path(call)
    mp3.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(call_wav), "-ac", "1",
                    "-ar", str(SAMPLE_RATE), "-c:a", "libmp3lame", "-b:a", "64k", str(mp3)], check=True)
    return mp3


def main():
    SAMPLES.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for call in CALLS:
            workdir = pathlib.Path(tmp) / call["file"]
            workdir.mkdir()
            mp3 = build(call, workdir)
            print(f"{mp3.relative_to(ROOT)}  {'upload' if call['upload'] else 'spare '}  {call['scenario']}", flush=True)
    manifest = [{k: call[k] for k in ("file", "scenario", "upload", "voices", "expected")} for call in CALLS]
    (SAMPLES / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
