# Presentation Feedback Agent

Analyzes presentation transcripts and provides intelligent feedback on confidence, delivery, and material quality.

## Quick Start

```cmd
cd agents\presentation_feedback_agent
run_presentation_feedback.bat
```

Test in new terminal:
```powershell
cd agents\presentation_feedback_agent
.\test_agent.ps1 test_sample.json
```

## Test Samples

- **test_sample.json** - AI healthcare (mixed quality, 18min)
- **test_sample_confident.json** - Blockchain (high quality, 8min)
- **test_sample_poor.json** - Quantum computing (many issues, 5min)
- **test_sample_technical.json** - Microservices (dense technical, 12min)

## Configuration

- **Port**: 5019
- **Model**: gemini-2.5-flash
- **API Key**: Set in `.env` at project root

## Troubleshooting

**Port in use**: Run `kill_port_5019.bat`
**Rate limit**: Wait 1-2 minutes
**Module error**: Ensure running from project root (batch file handles this)
