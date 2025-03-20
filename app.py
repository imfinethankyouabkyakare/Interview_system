import streamlit as st
import os
import time
import google.generativeai as genai
import agentops
import re
from guardrails import Guard
from guardrails.validators import ValidChoices

# Initialize AgentOps for monitoring
agentops.init(api_key="8d3d080d-d78e-460f-8d48-1194115ec670")

# Set up Google Gemini API
genai.configure(api_key="AIzaSyDq1wgsd_UjFTez-e8ptUDQlGBSAE-lmuM")

# Define alternative regex-based PII detection function
def detect_pii(text):
    pii_patterns = [
        r"\b\d{3}-\d{2}-\d{4}\b",  # SSN
        r"\b\d{16}\b",  # Credit Card
        r"\b\d{10}\b",  # Phone number
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"  # Email
    ]
    for pattern in pii_patterns:
        if re.search(pattern, text):
            return True
    return False

# Define manual blocklist filter
def blocklist_filter(text):
    blocklist = ["offensive", "discriminatory", "inappropriate"]
    return any(word in text.lower() for word in blocklist)

# Define guard for interview responses
guardrail_config = """
<rail version="0.1">
    <output>
        <string name="response" description="Ensures interview responses are appropriate and safe"/>
    </output>
    <validate>
        <ValidChoices name="response" choices="professional, technical, clarification"/>
    </validate>
</rail>
"""

# Create Guard from string
interview_guard = Guard.from_rail_string(guardrail_config)

# Define interview questions for different roles
interview_questions = {
    "Software Engineer": [
        "Explain the difference between inheritance and composition in object-oriented programming.",
        "How would you optimize a slow-performing SQL query?",
        "Describe a challenging technical problem you've solved and how you approached it."
    ],
    "Data Scientist": [
        "Explain the difference between supervised and unsupervised learning.",
        "How would you handle missing data in a dataset?",
        "Describe a project where you applied machine learning to solve a real-world problem."
    ],
    "Product Manager": [
        "How do you prioritize features in a product roadmap?",
        "Describe how you would validate a new product idea.",
        "How do you collaborate with engineering teams to ensure successful product delivery?"
    ]
}

def get_ai_response(question, job_role):
    """Get AI response with guardrails and monitoring"""
    try:
        trace = agentops.Trace(
            user_id="candidate_123",
            trace_id=f"interview_{int(time.time())}",
            metadata={"job_role": job_role, "question": question}
        )

        response = genai.generate(
            model="gemini-pro",
            prompt=f"You are an AI interviewer for a {job_role} position. Provide a response to the candidate's answer. Be professional and constructive.\n\nQuestion: {question}\n\nCandidate's Answer: [Candidate response would go here]",
            temperature=0.7,
            max_output_tokens=500
        )

        ai_response = response.text

        # Apply guardrails and PII detection
        if detect_pii(ai_response) or blocklist_filter(ai_response):
            validated = False
        else:
            validated_response = interview_guard.parse(ai_response)["response"]
            validated = True

        if validated:
            trace.log_event("response_validated", {"validation_status": "passed"})
        else:
            trace.log_event("response_validation_failed", {"validation_status": "failed", "original_response": ai_response})

        trace.end(status="completed")

        return validated_response if validated else "The response did not meet our safety guidelines. Please rephrase or try another question."
    except Exception as e:
        if 'trace' in locals():
            trace
