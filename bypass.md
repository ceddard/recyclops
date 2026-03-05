curl -X POST http://internal-recyclops-internal-1847805309.us-east-1.elb.amazonaws.com:8001/bypass \
  -H "Content-Type: application/json" \
  -d '{
    "repo": "ceddard/mecontrataaipfvr",
    "pr_number": 3,
    "reason": "Design review aprovado anteriormente",
    "created_by": "carlos",
    "expires_in_hours": 24
  }'