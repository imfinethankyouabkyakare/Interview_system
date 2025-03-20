import streamlit as st
import os
import time
import google.generativeai as genai
import agentops
import re
from guardrails import Guard
from guardrails.schema import Rail

# Initialize AgentOps for monitoring
agentops.init(api_key="your-agentops-api-key")

# Set up Google Gemini API
genai.configure(api_key="your-google-api-key")

# Define regex-based PII detection function
def detect_pii(text):
    pii_patterns = [
        r'\b\d{3}-\d{2}-\d{4}\b',  # SSN format
        r'\b(?:\d[ -]*?){13,16}\b',  # Credit card format
        r'\b\d{10}\b',  # Phone number
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'  # Email
    ]
    for pattern in pii_patterns:
        if re.search(pattern, text):
            return True
    return False

# Define regex-based blocklist filter
def blocklist_filter(text):
    blocklist = ["offensive", "discriminatory", "inappropriate"]
    return any(re.search(rf'\b{word}\b', text, re.IGNORECASE) for word in blocklist)

# Define guardrails using YAML format
guardrail_config = """
validators:
  - name: response_type
    type: choice
    choices:
      - professional
      - technical
      - clarification
"""

# Create Guard instance
rail = Rail(guardrail_config)
interview_guard = Guard.from_rail(rail)

# Define interview questions
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
            validated_response, validated = interview_guard.validate(ai_response)

        if validated:
            trace.log_event("response_validated", {"validation_status": "passed"})
        else:
            trace.log_event("response_validation_failed", {"validation_status": "failed", "original_response": ai_response})

        trace.end(status="completed")

        return validated_response if validated else "The response did not meet our safety guidelines. Please rephrase or try another question."
    except Exception as e:
        if 'trace' in locals():
            trace.log_event("error", {"error_message": str(e)})
            trace.end(status="error")
        return f"An error occurred: {str(e)}"

# Streamlit UI
st.title("AI Interview Platform")
st.subheader("Practice interviews with AI feedback and safety guardrails")

st.sidebar.header("Interview Settings")
job_role = st.sidebar.selectbox("Select Job Role", list(interview_questions.keys()))
candidate_name = st.sidebar.text_input("Your Name (Optional)")

if 'current_question_index' not in st.session_state:
    st.session_state.current_question_index = 0
if 'interview_history' not in st.session_state:
    st.session_state.interview_history = []

questions = interview_questions[job_role]
if st.session_state.current_question_index < len(questions):
    current_question = questions[st.session_state.current_question_index]

    st.markdown(f"### Question {st.session_state.current_question_index + 1}/{len(questions)}")
    st.markdown(f"**{current_question}**")

    candidate_response = st.text_area("Your Answer", height=150)

    if st.button("Submit Answer"):
        if candidate_response:
            trace_id = f"candidate_response_{int(time.time())}"
            trace = agentops.Trace(
                user_id=candidate_name if candidate_name else "anonymous_candidate",
                trace_id=trace_id,
                metadata={"job_role": job_role, "question_index": st.session_state.current_question_index}
            )
            trace.log_event("submitted_answer", {"question": current_question, "answer_length": len(candidate_response)})

            with st.spinner("AI is analyzing your response..."):
                ai_feedback = get_ai_response(current_question, job_role)

            st.session_state.interview_history.append({"question": current_question, "candidate_response": candidate_response, "ai_feedback": ai_feedback})

            st.session_state.current_question_index += 1
            trace.end(status="completed")
            st.experimental_rerun()
        else:
            st.warning("Please provide an answer before submitting.")
else:
    st.success("Interview completed! Here's a summary of your responses:")
    for i, item in enumerate(st.session_state.interview_history):
        st.markdown(f"### Question {i+1}")
        st.markdown(f"**{item['question']}**")
        st.markdown("Your answer:")
        st.info(item['candidate_response'])
        st.markdown("AI feedback:")
        st.success(item['ai_feedback'])

    if st.button("Start New Interview"):
        st.session_state.current_question_index = 0
        st.session_state.interview_history = []
        st.experimental_rerun()

st.sidebar.subheader("Interview Progress")
progress = st.sidebar.progress(min(st.session_state.current_question_index / len(questions), 1.0))
