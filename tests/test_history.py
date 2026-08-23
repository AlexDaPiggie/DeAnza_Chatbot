"""The testcases in this file is to test if the model is able to retrieve the correct context for follow-up questions and answer without hallucination"""

import asyncio
from core.chat import stream_chat, condense_query_with_history

async def test_multi_turn_flow():
    print ("Test 1: Condesne query")
    history  = [
        {
            "role": "user", 
            "content": "What is CIS22A?"
        },
        {
            "role": "assistant", 
            "content": "CIS 22A is Beginning Programming Methodologies in C++ at De Anza College.", 
        }
    ]

    follow_up = "What are its prerequisites?"
    condensed = condense_query_with_history(follow_up, history)
    print (f"Original Follow-up: '{follow_up}'")
    print (f"Condensed Query: '{condensed}'\n")

    assert "CIS 22A" in condensed or "22A" in condensed or "C++" in condensed


    print ("Test 2: Entire Multi-turn Streaming")
    response_tokens = []
    async for token in stream_chat(follow_up, history): 
        response_tokens.append(token)

    full_answer = "".join (response_tokens)
    print (f"Assitant Answer: \n{full_answer[:300]}...\n")

    assert len(full_answer) > 20 
    print ("Multi turn backend memory testcase passed")

if __name__ == "__main__":
    asyncio.run(test_multi_turn_flow())
    