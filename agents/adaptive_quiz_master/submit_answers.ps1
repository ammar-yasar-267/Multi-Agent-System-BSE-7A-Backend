$body = @{
    quiz_id = "7a0883b8-cefa-4ee8-b087-dc713122db76"
    user_id = "user789"
    answers = @(
        0,  # Q1: py_loop_001 - Correct (0,1,2)
        2,  # Q2: py_loop_009 - Incorrect (should be 1)
        1,  # Q3: py_loop_005 - Correct (continue)
        1,  # Q4: py_loop_008 - Incorrect (should be 0)
        0,  # Q5: py_loop_002 - Correct (1,2,3,4)
        1,  # Q6: py_loop_010 - Incorrect (should be 0)
        0,  # Q7: py_loop_003 - Correct (0,1,2)
        0   # Q8: py_loop_006 - Incorrect (should be 0)
    )
} | ConvertTo-Json -Depth 10

try {
    $response = Invoke-RestMethod -Uri "http://localhost:5020/submit_answers" -Method Post -ContentType "application/json" -Body $body -TimeoutSec 30
    $response | ConvertTo-Json -Depth 10 | Write-Output
}
catch {
    Write-Error "Request failed: $_"
}