import streamlit as st
import os
import time
import google.generativeai as genai
import agentops
import re
from pydantic import BaseModel, ValidationError

# Initialize AgentOps for monitoring - using a different initialization pattern
AGENTOPS_API_KEY = '8d3d080d-d78e-460f-8d48-1194115ec670'
agentops.init(
    api_key=AGENTOPS_API_KEY,
    default_tags=['gemini']
)
agentops.start_session()

# Set up Google Gemini API
genai.configure(api_key="AIzaSyDq1wgsd_UjFTez-e8ptUDQlGBSAE-lmuM")

# Define regex-based PII detection function
def detect_pii(text):
    pii_patterns = [
        r"\b\d{3}-\d{2}-\d{4}\b",  # SSN (XXX-XX-XXXX)
        r"\b\d{16}\b",  # Credit card number
        r"\b\d{10}\b",  # Phone number
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b",  # Email
    ]
    for pattern in pii_patterns:
        if re.search(pattern, text):
            return True
    return False

# Define manual blocklist filter
def blocklist_filter(text):
    blocklist = ["offensive", "discriminatory", "inappropriate"]
    return any(word in text.lower() for word in blocklist)

# Define a Pydantic model for validation
class AIResponse(BaseModel):
    response: str

    @classmethod
    def validate_response(cls, text):
        try:
            validated_response = cls(response=text)
            return validated_response.response, True
        except ValidationError:
            return "The response is invalid.", False

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
    """Get AI response with validation and monitoring"""
    try:
        # Use the current AgentOps API
        trace_id = f"interview_{int(time.time())}"
        
        # Log the event using AgentOps
        agentops.log_event(
            event_name="interview_request",
            metadata={
                "user_id": "candidate_123", 
                "trace_id": trace_id,
                "job_role": job_role, 
                "question": question
            }
        )

        response = genai.generate(
            model="gemini-pro",
            prompt=f"You are an AI interviewer for a {job_role} position. Provide a response to the candidate's answer. Be professional and constructive.\n\nQuestion: {question}\n\nCandidate's Answer: [Candidate response would go here]",
            temperature=0.7,
            max_output_tokens=500
        )

        ai_response = response.text

        # Apply validation and PII detection
        if detect_pii(ai_response) or blocklist_filter(ai_response):
            validated = False
            validated_response = "The response did not meet our safety guidelines. Please rephrase or try another question."
            
            agentops.log_event(
                event_name="response_validation_failed",
                metadata={
                    "trace_id": trace_id,
                    "reason": "PII or blocklist detected"
                }
            )
        else:
            validated_response, validated = AIResponse.validate_response(ai_response)
            
            if validated:
                agentops.log_event(
                    event_name="response_validated",
                    metadata={
                        "trace_id": trace_id,
                        "validation_status": "passed"
                    }
                )
            else:
                agentops.log_event(
                    event_name="response_validation_failed",
                    metadata={
                        "trace_id": trace_id,
                        "validation_status": "failed",
                        "original_response": ai_response
                    }
                )

        return validated_response
    except Exception as e:
        error_msg = f"An error occurred: {str(e)}"
        
        agentops.log_event(
            event_name="error",
            metadata={
                "trace_id": trace_id if 'trace_id' in locals() else "unknown",
                "error_message": str(e)
            }
        )
        
        return error_msg

# Streamlit UI
st.title("AI Interview Platform")
st.subheader("Practice interviews with AI feedback and validation")

st.sidebar.header("Interview Settings")
job_role = st.sidebar.selectbox("Select Job Role", list(interview_questions.keys()))
candidate_name = st.sidebar.text_input("Your Name (Optional)")

# Model selection
model_options = {"Gemini Pro": "gemini-pro"}
selected_model = st.sidebar.selectbox("Select Model", list(model_options.keys()))

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
            
            # Log submission with AgentOps
            agentops.log_event(
                event_name="submitted_answer",
                metadata={
                    "user_id": candidate_name if candidate_name else "anonymous_candidate",
                    "trace_id": trace_id,
                    "job_role": job_role,
                    "question_index": st.session_state.current_question_index,
                    "model": model_options[selected_model],
                    "question": current_question,
                    "answer_length": len(candidate_response)
                }
            )

            with st.spinner("AI is analyzing your response..."):
                ai_feedback = get_ai_response(current_question, job_role)

            st.session_state.interview_history.append({
                "question": current_question, 
                "candidate_response": candidate_response, 
                "ai_feedback": ai_feedback, 
                "model": selected_model
            })

            # Log completion with AgentOps
            agentops.log_event(
                event_name="question_completed",
                metadata={
                    "trace_id": trace_id,
                    "question_index": st.session_state.current_question_index
                }
            )

            st.session_state.current_question_index += 1
            st.experimental_rerun()
        else:
            st.warning("Please provide an answer before submitting.")
else:
    st.success("Interview completed! Here's a summary of your responses:")

    # Display interview history
    for i, entry in enumerate(st.session_state.interview_history):
        st.markdown(f"### Question {i+1}: {entry['question']}")
        st.markdown("**Your Answer:**")
        st.markdown(entry['candidate_response'])
        st.markdown("**AI Feedback:**")
        st.markdown(entry['ai_feedback'])
        st.markdown("---")
    
    # Log interview completion
    agentops.log_event(
        event_name="interview_completed",
        metadata={
            "user_id": candidate_name if candidate_name else "anonymous_candidate",
            "job_role": job_role,
            "questions_answered": len(st.session_state.interview_history)
        }
    )
