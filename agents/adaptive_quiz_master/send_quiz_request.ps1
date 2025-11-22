$body = @{
    message_id = "msg-test-003"
    sender = "SupervisorAgent_Main"
    recipient = "AdaptiveQuizMasterAgent"
    type = "task_assignment"
    task = @{
        name = "generate_adaptive_quiz"
        priority = 1
        parameters = @{
            agent_name = "adaptive_quiz_master_agent"
            intent = "generate_adaptive_quiz"
            payload = @{
                user_info = @{
                    user_id = "user789"
                    name = "Alex Smith"
                    learning_level = "beginner"
                }
                quiz_request = @{
                    topic = "Python Loops"
                    num_questions = 10
                    question_types = @("mcq", "true_false", "short_answer")
                    bloom_taxonomy_level = "remember"
                    adaptive = $true
                }
                session_info = @{
                    session_id = "sess-test-003"
                    timestamp = "2025-11-15T18:59:00Z"
                    source = "supervisor_agent"
                }
            }
        }
    }
} | ConvertTo-Json -Depth 10

try {
    $response = Invoke-RestMethod -Uri "http://localhost:5020/process" -Method Post -ContentType "application/json" -Body $body -TimeoutSec 30
    $response | ConvertTo-Json -Depth 10 | Write-Output
}
catch {
    Write-Error "Request failed: $_"
}