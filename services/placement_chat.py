from services.placement_llm import ask_placement_agent, is_small_talk


def get_chat_response(context, history, message):
    return ask_placement_agent(context, history, message)
