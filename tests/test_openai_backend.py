import langchain
import pytest
from langchain.chat_models import ChatOpenAI

from flows.base_flows import OpenAIChatAtomicFlow
from flows.messages import TaskMessage
from flows.messages.chat_message import ChatMessage
from tests.mocks import MockChatOpenAI, MockBrokenChatOpenAI, MockAnnotator
import time

def test_success(monkeypatch):
    monkeypatch.setattr(langchain.chat_models, "ChatOpenAI", MockChatOpenAI)
    monkeypatch.setattr(time, "sleep", lambda x: None)

    expected_out = ["answer"]
    expected_in = ["question"]
    sys_prompt = {
        "_target_": "langchain.PromptTemplate",
        "template": "You are a helpful assistant",
        "input_variables": []
    }

    hum_prompt = {
        "_target_": "langchain.PromptTemplate",
        "template": "Please respond nicely",
        "input_variables": []
    }

    query_prompt = {
        "_target_": "langchain.PromptTemplate",
        "template": "Bam, code",
        "input_variables": []
    }

    gen_flow_dict = {
        "_target_": "flows.base_flows.OpenAIChatAtomicFlow",
        "name": "gen_flow",
        "description": "gen_desc",
        "expected_inputs": ["input_0", "input_1"],
        "expected_outputs": ["gen_out"],
        "model_name": "gpt-model",
        "generation_parameters": {"temperature": 0.7},
        "system_message_prompt_template": sys_prompt,
        "human_message_prompt_template": hum_prompt,
        "query_message_prompt_template": query_prompt,
        "response_annotators" : {"answer": {"_target_": "tests.mocks.MockAnnotator", "key": "answer"}}

    }

    openai_flow = OpenAIChatAtomicFlow(**gen_flow_dict)

    answer_annotator = openai_flow._get_annotator_with_key("answer")
    assert answer_annotator is not None

    openai_flow.set_api_key("foo")

    task_message = openai_flow.package_task_message(openai_flow, "test", {"question": "What is your answer?"}, expected_out)
    output = openai_flow(task_message)
    assert "answer" in output.data


def test_failure(monkeypatch):
    monkeypatch.setattr(langchain.chat_models, "ChatOpenAI", MockBrokenChatOpenAI)
    monkeypatch.setattr(time, "sleep", lambda x: None)

    expected_out = ["answer"]
    expected_in = ["question"]
    sys_prompt = {
        "_target_": "langchain.PromptTemplate",
        "template": "You are a helpful assistant",
        "input_variables": []
    }

    hum_prompt = {
        "_target_": "langchain.PromptTemplate",
        "template": "Please respond nicely",
        "input_variables": []
    }

    query_prompt = {
        "_target_": "langchain.PromptTemplate",
        "template": "Bam, code",
        "input_variables": []
    }

    gen_flow_dict = {
        "_target_": "flows.base_flows.OpenAIChatAtomicFlow",
        "name": "gen_flow",
        "description": "gen_desc",
        "expected_inputs": ["input_0", "input_1"],
        "expected_outputs": ["gen_out"],
        "model_name": "gpt-model",
        "generation_parameters": {"temperature": 0.7},
        "system_message_prompt_template": sys_prompt,
        "human_message_prompt_template": hum_prompt,
        "query_message_prompt_template": query_prompt,

    }

    openai_flow = OpenAIChatAtomicFlow(**gen_flow_dict)

    openai_flow.set_api_key("foo")

    task_message = openai_flow.package_task_message(openai_flow, "test", {"question": "What is your answer?"},
                                                    expected_out)

    # the following call raises an exception
    # expect it with pytest
    with pytest.raises(Exception):
        output = openai_flow(task_message)





def test_conv_init(monkeypatch):
    monkeypatch.setattr(langchain.chat_models, "ChatOpenAI", MockChatOpenAI)
    monkeypatch.setattr(time, "sleep", lambda x: None)

    expected_out = ["answer"]
    sys_prompt = {
        "_target_": "langchain.PromptTemplate",
        "template": "You are a helpful assistant",
        "input_variables": []
    }

    hum_prompt = {
        "_target_": "langchain.PromptTemplate",
        "template": "Please respond nicely",
        "input_variables": []
    }

    query_prompt = {
        "_target_": "langchain.PromptTemplate",
        "template": "Bam, code",
        "input_variables": []
    }

    gen_flow_dict = {
        "_target_": "flows.base_flows.OpenAIChatAtomicFlow",
        "name": "gen_flow",
        "description": "gen_desc",
        "expected_inputs": ["input_0", "input_1"],
        "expected_outputs": ["gen_out"],
        "model_name": "gpt-model",
        "generation_parameters": {"temperature": 0.7},
        "system_message_prompt_template": sys_prompt,
        "human_message_prompt_template": hum_prompt,
        "query_message_prompt_template": query_prompt,

    }

    openai_flow = OpenAIChatAtomicFlow(**gen_flow_dict)

    openai_flow.set_api_key("foo")

    task_message = openai_flow.package_task_message(openai_flow, "test", {"query": "What is your answer?"},
                                                    expected_out)


    _ = openai_flow(task_message)

    expected_inputs = openai_flow.expected_inputs_given_state()

    for key in expected_inputs:
        assert key in task_message.data.keys()
    _ = openai_flow(task_message)


def test_inspect_conversation(monkeypatch):
    monkeypatch.setattr(langchain.chat_models, "ChatOpenAI", MockChatOpenAI)

    expected_out = ["answer"]
    expected_in = ["question"]

    system_message_prompt_template = langchain.PromptTemplate(
        template="You are an assistant",
        input_variables=[]
    )

    human_message_prompt_template = langchain.PromptTemplate(
        template="{{query}}",
        input_variables=["query"],
        template_format="jinja2"
    )

    query_message_prompt_template = langchain.PromptTemplate(
        template="Here is my question: {{question}}",
        input_variables=["question"],
        template_format="jinja2"
    )

    openai_flow = OpenAIChatAtomicFlow(
        name="openai",
        description="openai",
        model_name="doesn't exist",
        expected_outputs=expected_out,
        expected_inputs=expected_in,
        generation_parameters={},
        system_message_prompt_template=system_message_prompt_template,
        human_message_prompt_template=human_message_prompt_template,
        query_message_prompt_template=query_message_prompt_template,
        wait_time_between_retries=0,
    )

    openai_flow.initialize()
    openai_flow.set_api_key("foo")

    task_message = TaskMessage(
        expected_output_keys=expected_out,
        target_flow_run_id=openai_flow.state["flow_run_id"],
        message_creator="task",
        parent_message_ids=[],
        flow_runner="task",
        flow_run_id="00",
        data={"question": "What is your answer?"},
    )
    output = openai_flow(task_message)
    assert "answer" in output.data

    openai_flow.get_conversation_messages(openai_flow.state['flow_run_id'])
    with pytest.raises(ValueError):
        openai_flow.get_conversation_messages("foo", message_format="unknown message format")

    with pytest.raises(ValueError):
        message = ChatMessage(flow_run_id=openai_flow.state['flow_run_id'], message_creator="unknown message creator")
        openai_flow.history.messages.append(message)
        openai_flow.get_conversation_messages(openai_flow.state['flow_run_id'], message_format="open_ai")


def test_add_demonstration(monkeypatch):
    monkeypatch.setattr(langchain.chat_models, "ChatOpenAI", MockChatOpenAI)

    expected_out = ["answer"]
    expected_in = ["question"]

    system_message_prompt_template = langchain.PromptTemplate(
        template="You are an assistant",
        input_variables=[]
    )

    human_message_prompt_template = langchain.PromptTemplate(
        template="{{query}}",
        input_variables=["query"],
        template_format="jinja2"
    )

    query_message_prompt_template = langchain.PromptTemplate(
        template="Here is my question: {{question}}",
        input_variables=["question"],
        template_format="jinja2"
    )

    demonstrations_response_template = langchain.PromptTemplate(
        template="The answer is: {{answer}}",
        input_variables=["answer"],
        template_format="jinja2"
    )

    openai_flow = OpenAIChatAtomicFlow(
        name="openai",
        description="openai",
        model_name="doesn't exist",
        expected_outputs=expected_out,
        expected_inputs=expected_in,
        generation_parameters={},
        system_message_prompt_template=system_message_prompt_template,
        human_message_prompt_template=human_message_prompt_template,
        query_message_prompt_template=query_message_prompt_template,
        wait_time_between_retries=0,
        demonstrations_response_template=demonstrations_response_template,
        demonstrations=[{"question": "What is your answer?", "answer": "My answer is 42"}],
    )

    openai_flow.initialize()
    openai_flow.set_api_key("foo")

    task_message = TaskMessage(
        expected_output_keys=expected_out,
        target_flow_run_id=openai_flow.state["flow_run_id"],
        message_creator="task",
        parent_message_ids=[],
        flow_runner="task",
        flow_run_id="00",
        data={"question": "What is your answer?"},
    )
    output = openai_flow(task_message)
    assert "answer" in output.data

    openai_flow.get_conversation_messages(openai_flow.state['flow_run_id'])


def test_response_annotator(monkeypatch):
    monkeypatch.setattr(langchain.chat_models, "ChatOpenAI", MockChatOpenAI)

    expected_out = ["answer"]
    expected_in = ["question"]

    system_message_prompt_template = langchain.PromptTemplate(
        template="You are an assistant",
        input_variables=[]
    )

    human_message_prompt_template = langchain.PromptTemplate(
        template="{{query}}",
        input_variables=["query"],
        template_format="jinja2"
    )

    query_message_prompt_template = langchain.PromptTemplate(
        template="Here is my question: {{question}}",
        input_variables=["question"],
        template_format="jinja2"
    )

    openai_flow = OpenAIChatAtomicFlow(
        name="openai",
        description="openai",
        model_name="doesn't exist",
        expected_outputs=expected_out,
        expected_inputs=expected_in,
        generation_parameters={},
        system_message_prompt_template=system_message_prompt_template,
        human_message_prompt_template=human_message_prompt_template,
        query_message_prompt_template=query_message_prompt_template,
        wait_time_between_retries=0,
        response_annotators={"answer": MockAnnotator("answer")}
    )

    answer_annotator = openai_flow._get_annotator_with_key("answer")
    assert answer_annotator is not None

    openai_flow.initialize()
    openai_flow.set_api_key("foo")

    task_message = TaskMessage(
        expected_output_keys=expected_out,
        target_flow_run_id=openai_flow.state["flow_run_id"],
        message_creator="task",
        parent_message_ids=[],
        flow_runner="task",
        flow_run_id="00",
        data={"question": "What is your answer?"},
    )
    output = openai_flow(task_message)
    assert "answer" in output.data

    openai_flow.get_conversation_messages(openai_flow.state['flow_run_id'])


def test_response_annotator_wrong_key(monkeypatch):
    monkeypatch.setattr(langchain.chat_models, "ChatOpenAI", MockChatOpenAI)

    expected_out = ["answer"]
    expected_in = ["question"]

    system_message_prompt_template = langchain.PromptTemplate(
        template="You are an assistant",
        input_variables=[]
    )

    human_message_prompt_template = langchain.PromptTemplate(
        template="{{query}}",
        input_variables=["query"],
        template_format="jinja2"
    )

    query_message_prompt_template = langchain.PromptTemplate(
        template="Here is my question: {{question}}",
        input_variables=["question"],
        template_format="jinja2"
    )

    openai_flow = OpenAIChatAtomicFlow(
        name="openai",
        description="openai",
        model_name="doesn't exist",
        expected_outputs=expected_out,
        expected_inputs=expected_in,
        generation_parameters={},
        system_message_prompt_template=system_message_prompt_template,
        human_message_prompt_template=human_message_prompt_template,
        query_message_prompt_template=query_message_prompt_template,
        wait_time_between_retries=0,
        response_annotators={"answer": MockAnnotator("wrong key")}
    )

    openai_flow.initialize()
    openai_flow.set_api_key("foo")

    task_message = TaskMessage(
        expected_output_keys=expected_out,
        target_flow_run_id=openai_flow.state["flow_run_id"],
        message_creator="task",
        parent_message_ids=[],
        flow_runner="task",
        flow_run_id="00",
        data={"question": "What is your answer?"},
    )
    output = openai_flow(task_message)
    assert "answer" in output.data

    openai_flow.get_conversation_messages(openai_flow.state['flow_run_id'])
