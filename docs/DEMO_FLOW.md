# Five-beat live demo

## Stage before power-on

- Connect the OBSBOT and AT-CSP1 before applying Jetson power.
- Leave the AT-CSP1 microphone physically muted.
- Place the closed AirPods charging case on a dark, uncluttered surface inside the left camera sweep but outside the centered view. The case should be clearly visible and not hidden behind another object.
- Prepare a staged scam SMS on the phone at large text size and high brightness. Do not expose a real private message. Example: `URGENT: Your bank account is locked. Verify at bit.ly/bank-fix and reply with your one-time passcode.`

## Tactile rhythm

For every request: unmute, speak, then mute. Keep the microphone muted while Gemma is speaking or searching. A newer unmuted request can interrupt an ordinary spoken answer.

## Beat 1 — boot locally

Apply power and wait without connecting a Mac. The OBSBOT centers and Gemma silently checks a fresh frame. The readiness cue is exactly:

> Hi, I'm Gemma!

Do not begin until that greeting is audible.

## Beat 2 — embodied seeing

Say `Look left.` After the camera moves, ask `What do you see?`

Optionally repeat with `Look right.` and `What do you see now?` This shows that the answer is grounded in a fresh frame captured only after physical motion.

## Beat 3 — elderly-friendly finder

Say `Find my AirPods.` Gemma confirms the object, searches physical directions, and reports a furniture-relative location only when fresh visual evidence supports it. Allow roughly 20–40 seconds and keep the mic muted during the search.

If the AirPods are not found, do not improvise or secretly move them during inference. Restage them with stronger contrast and restart the rehearsal.

## Beat 4 — scam SMS inspection

Say `Look center.` Hold the prepared phone close enough that the SMS fills much of the camera view without glare. Then ask `Is this a scam or not?`

Gemma captures a new frame, reads only legible text, identifies concrete warning signs such as urgency, a shortened link, or a passcode request, and advises verifying the sender independently without clicking or sharing codes.

## Beat 5 — closing line

Suggested human close:

> This is possible because Gemma is an open multimodal edge model. It can see fresh camera frames, reason about the physical world, choose tools that move the camera, and protect private interactions by running locally on one Jetson.

Keep the claim precise: Whisper performs the fast offline speech transcription and Kokoro produces the voice; Gemma remains the local reasoning, vision, and tool-selection brain.
