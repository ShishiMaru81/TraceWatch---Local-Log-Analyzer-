param([Parameter(Mandatory=$true)][string]$StoryPath)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$taskStory = Get-Content -LiteralPath $StoryPath -Raw -Encoding UTF8 | ConvertFrom-Json
$taskVoice = New-Object System.Speech.Synthesis.SpeechSynthesizer
$taskVoice.Rate = 0
try {
    foreach ($taskSlide in $taskStory) {
        $taskVoice.SetOutputToWaveFile([string]$taskSlide.audio)
        $taskVoice.Speak([string]$taskSlide.narration)
        $taskVoice.SetOutputToNull()
    }
} finally {
    $taskVoice.Dispose()
}
