# Security Policy for BrainBot

## Overview

BrainBot implements a comprehensive two-model safety architecture designed for child protection. This document describes our security approach, safety mechanisms, and responsible AI practices.

## ⚠️ Important Disclaimer

**BrainBot is designed for family/education use with on-device safeguards. Parental supervision is recommended. No guarantee all unsafe content is prevented.**

While we implement multiple layers of safety, no AI system is perfect. Parents should:
- Supervise usage, especially for younger children
- Review conversation logs periodically
- Report any concerning outputs
- Keep the safety system enabled

## 🛡️ Safety Architecture

### Two-Model System

BrainBot uses a dual-model architecture for enhanced safety:

1. **Generation Model**: TinyLlama 1.1B (existing) - Creates responses
2. **Moderation Model**: Guard model (8B-class GGUF) - Filters input/output

Both models run locally on your device. No data is sent to external servers.

### Safety Flow

```
User Input → Input Moderation → Generation → Output Moderation → Display
                ↓ (blocked)                      ↓ (blocked)
            Block Message                    Safe Rewrite → Re-moderate
                                                   ↓ (still unsafe)
                                              Block Message
```

## 🔒 Safety Categories

The system monitors for and blocks:

- `sexual_content` - Any sexual or romantic content
- `sexual_minors` - Any content sexualizing minors
- `self_harm` - Self-harm ideation or instructions
- `violence` - Graphic violence or instructions to harm
- `weapons_illicit` - Weapons construction or illegal items
- `hate_abuse` - Hate speech, bullying, harassment
- `drugs_alcohol` - Substance use or acquisition
- `medical_advice` - Medical diagnosis or treatment advice
- `privacy_personal_data` - PII exposure or doxxing
- `other_sensitive` - Other inappropriate content

## 🎯 Allow-List Topics

BrainBot focuses on educational topics appropriate for children:

### Under 13 (Strictest)
- Math and basic arithmetic
- Animals and nature
- Space and astronomy
- Simple word games
- Clean jokes and riddles
- Art and music
- Weather

### Teens (13-17)
All of the above plus:
- Basic science (non-graphic)
- Geography and cultures
- History (age-appropriate)
- Creative writing
- Environmental science
- Sports (non-violent)
- Computer basics

## 🚨 Crisis Intervention

When self-harm, abuse, or severe distress is detected:

1. Conversation immediately stops
2. Crisis resources card displays
3. Local helpline information shown
4. Chat locked until parent PIN entered
5. Incident logged (locally only)

**Crisis Resources Displayed:**
- Talk to a parent or guardian
- Contact school counselor
- Local emergency services
- Age-appropriate helplines

## 🔐 Parental Controls

### Age Gate & PIN System

- **First Run**: Parent must set age band and PIN
- **PIN Protection**: Settings and transcript access
- **Age Bands**: Under 13, Teen (13-17), Adult
- **Lockout**: 3 failed attempts = 15-minute lockout

### Data Handling

- **Transcripts**: OFF by default
- **Export**: Requires parent PIN
- **Storage**: Local only, never uploaded
- **Analytics**: NONE - no telemetry collected

## 🧪 Testing & Validation

### Red-Team Test Coverage

Our test suite (`tests/test_safety.py`) validates blocking of:

- Explicit content (including obfuscated)
- Self-harm and crisis situations
- Violence and weapons
- Medical advice requests
- PII extraction attempts
- Grooming patterns
- Bullying/harassment
- Non-English inputs (when not supported)

### Continuous Testing

```bash
# Run safety tests
pytest tests/test_safety.py -v

# Test with coverage
pytest tests/test_safety.py --cov=safety
```

## 🔧 Configuration

### Environment Variables

```bash
# Port configuration
export GEN_PORT=8080  # Generation model port
export MOD_PORT=8081  # Moderation model port

# Safety toggle (for development only)
export BRAINBOT_SAFETY=true  # Default: true
```

### Model Parameters

Generation (Conservative):
- Temperature: 0.2-0.4
- Top-p: 0.8
- Max tokens: 200
- Repeat penalty: On

Moderation (Strict):
- Temperature: 0.0
- Top-p: 0.1
- GBNF grammar enforced
- Deterministic output

## 📊 Safety Metrics

The system tracks (locally only):
- Blocked prompts count
- Crisis interventions
- Category frequencies
- Session duration
- No content is logged by default

## 🐛 Reporting Issues

### Security Vulnerabilities

If you discover a security vulnerability:

1. DO NOT open a public issue
2. Email: [security contact]
3. Include:
   - Description of vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

### False Positives/Negatives

Report content that was incorrectly allowed or blocked:
1. Open a GitHub issue (sanitize examples)
2. Include age band setting
3. Describe expected vs actual behavior

## 🔄 Fail-Closed Design

All safety systems fail closed:

- **Guard server down**: Block all content
- **JSON parse error**: Treat as blocked
- **Network timeout**: Block content
- **Invalid model response**: Block content
- **Any exception**: Default to blocking

## 🌐 Internationalization

Currently, BrainBot safety system:
- Supports English only
- Blocks non-English input with friendly message
- Plans for multilingual support in future

## 📝 Compliance Notes

BrainBot is designed with privacy and safety in mind:

- **COPPA**: No data collection from users under 13
- **GDPR**: All processing is local, no data transferred
- **Educational Use**: Appropriate for classroom settings
- **Open Source**: Full transparency of safety mechanisms

## ⚖️ Ethical AI Principles

1. **Transparency**: Open source, auditable code
2. **Privacy**: Local-only processing
3. **Safety**: Multiple protective layers
4. **Fairness**: Consistent moderation
5. **Accountability**: Clear documentation
6. **Human Oversight**: Parent controls required

## 🔮 Future Enhancements

Planned safety improvements:
- [ ] Multilingual safety support
- [ ] Adjustable sensitivity levels
- [ ] Custom block/allow lists
- [ ] Conversation sentiment analysis
- [ ] Time-based usage limits
- [ ] Educational safety mode

## 📚 Additional Resources

- [SETUP_PI.md](SETUP_PI.md) - Raspberry Pi setup
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common issues
- [tests/test_safety.py](../tests/test_safety.py) - Safety test suite

---

**Remember**: Technology is a tool to assist, not replace, parental supervision and open communication with children about online safety.