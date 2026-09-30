import os
import uuid

import streamlit as st

if "GEMINI_API_KEY" in st.secrets:
	os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]

from zypheris import get_history, load_memory, model, save_memory, to_gemini_history


@st.cache_resource
def initialize_memory():
	load_memory()
	return True


initialize_memory()


st.set_page_config(page_title="Zypheris", page_icon="⚡")
st.title("⚡ Zypheris")
st.caption("A Gemini assistant with persistent conversation memory")


if "messages" not in st.session_state:
	if "conversation_id" not in st.session_state:
		st.session_state.conversation_id = uuid.uuid4().int
	history = get_history(st.session_state.conversation_id)
	st.session_state.messages = [
		{"role": entry["role"], "content": entry["text"]}
		for entry in history
		if entry.get("text")
	]


for message in st.session_state.messages:
	with st.chat_message(message["role"]):
		st.markdown(message["content"])


prompt = st.chat_input("Message Zypheris")
if prompt:
	st.session_state.messages.append({"role": "user", "content": prompt})
	with st.chat_message("user"):
		st.markdown(prompt)

	with st.chat_message("assistant"):
		with st.spinner("Thinking..."):
			try:
				history = get_history(st.session_state.conversation_id)
				chat = model.start_chat(history=to_gemini_history(history))
				response = chat.send_message(prompt)
				reply_text = response.text.strip() if response.text else "I couldn't generate a response."
			except Exception as error:
				reply_text = f"I couldn't connect to Gemini: {error}"

			st.markdown(reply_text)

	history = get_history(st.session_state.conversation_id)
	history.append({"role": "user", "text": prompt})
	history.append({"role": "model", "text": reply_text})
	save_memory()
