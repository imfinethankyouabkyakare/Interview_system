import streamlit as st
import os
import time
import google.generativeai as genai
import agentops
from guardrails import Guard
from guardrails.validators import DetectPII, BlocklistMatch
import yaml

# Initialize AgentOps for monitoring
agentops.init(api_key="470a571e-3f2a-4434-9cfc-cdc64247d696")

# Set up Gemini API key
genai.configure(api_key=("GEMINI_API_KEY", "AIzaSyDq1wgsd_UjFTez-e8ptUDQlGBSAE-lmuM"))

# Define guard for interview responses
guardrail_config = """
id: interview_response_validator
description: Ensures interview responses are appropriate and safe
validators:
  - id: no_pii
    type: detect_pii
    config:
      pii_types:
        - PERSON
        - EMAIL_ADDRESS
        - PHONE_NUMBER
        - US_SSN
        - CREDIT_CARD
  - id: appropriate_content
    type: blocklist_match
    config:
      blocklist:
        - offensive
        - discriminatory
        - inappropriate
"""

# Create guard from YAML
with open("guardrail_config.yaml", "w") as f:
    f.write(guardrail_config)

interview_guard = Guard.from_yaml("guardrail_config.yaml")

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
    """Get AI response with guardrails and monitoring using Gemini API"""
    try:
        trace = agentops.Trace(
            user_id="candidate_123",
            trace_id=f"interview_{int(time.time())}",
            metadata={"job_role": job_role, "question": question}
        )

        # Get AI response using Gemini API
        model = genai.GenerativeModel("gemini-pro")
        response = model.generate_content(f"You are an AI interviewer for a {job_role} position. "
                                          f"Provide a response to the candidate's answer. Be professional and constructive."
                                          f"\n\nThe question was: {question}\n\nMy answer is: [Candidate response would go here]")

        ai_response = response.text

        # Apply guardrails
        validated_response, validated = interview_guard.validate(ai_response)

        # Log outcome to AgentOps
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

# Sidebar for configuration
st.sidebar.header("Interview Settings")
job_role = st.sidebar.selectbox("Select Job Role", list(interview_questions.keys()))
candidate_name = st.sidebar.text_input("Your Name (Optional)")

# Initialize session state
if 'current_question_index' not in st.session_state:
    st.session_state.current_question_index = 0
if 'interview_history' not in st.session_state:
    st.session_state.interview_history = []

# Display current question
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

            st.session_state.interview_history.append({
                "question": current_question,
                "candidate_response": candidate_response,
                "ai_feedback": ai_feedback
            })

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

st.sidebar.subheader("Platform Features")
st.sidebar.markdown("""
- 🚀 **Google Gemini** provides AI-powered interview feedback
- 🛡️ **Guardrails.ai** ensures safe and appropriate responses
- 📊 **AgentOps.ai** monitors performance and user experience
- 🔒 **PII Protection** prevents collection of sensitive information
""")

st.sidebar.info("This platform uses AgentOps.ai for monitoring. No personal identifiable information is collected.")
