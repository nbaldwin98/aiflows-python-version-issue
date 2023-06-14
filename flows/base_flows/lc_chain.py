from typing import Dict, Any, List

from langchain import OpenAI
from langchain.chains.base import Chain
from langchain.memory import ConversationBufferMemory

from flows.base_flows import AtomicFlow


class GenericLCChain(AtomicFlow):
    lc_chain: Chain

    def __init__(self, lc_chain: Chain, **kwargs):
        if "expected_inputs" not in kwargs:
            kwargs["expected_inputs"] = lc_chain.input_keys
        else:
            assert set(lc_chain.input_keys).issubset(set(kwargs["expected_inputs"]))

        if "expected_outputs" not in kwargs:
            kwargs["expected_outputs"] = lc_chain.output_keys
        else:
            assert set(lc_chain.output_keys).issubset(set(kwargs["expected_outputs"]))

        super().__init__(
            namespace_clearing_after_run=False,
            **kwargs
        )

        self.KEYS_TO_IGNORE_HASH += ["lc_chain"]  # but needs to override __repr__ to have meaningful hash
        self.lc_chain = lc_chain
        self.lc_chain.verbose = self.verbose

    # def __repr__(self):
    #     # override for caching, needs to repr that without repr all sub-object with their pointers
    #     # type_of_vectorstore = self.vector_db.vectorstore.__class__.__name__
    #     return

    def run(self, input_data: Dict[str, Any], expected_outputs: List[str]) -> Dict[str, Any]:
        answer = self.lc_chain.run(input_data)
        ## ToDo: sync the langchain memory into the history of the atomic flow, need to retrieve system_prompt

        # LangChain chains require 1 expected output
        return {expected_outputs[0]: answer}


if __name__ == "__main__":
    from langchain.document_loaders import TextLoader
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain.embeddings import OpenAIEmbeddings
    from langchain.vectorstores import Chroma
    from langchain.chains import RetrievalQA, ConversationalRetrievalChain

    loader = TextLoader('data/state_of_the_union.txt', encoding='utf8')
    documents = loader.load()

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=0)
    texts = text_splitter.split_documents(documents)

    embeddings = OpenAIEmbeddings()

    memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

    db = Chroma.from_documents(texts, embeddings)
    qa_with_docs = ConversationalRetrievalChain.from_llm(OpenAI(temperature=0), db.as_retriever(), memory=memory)
    # qa = RetrievalQA.from_chain_type(llm=OpenAI(), chain_type="stuff", retriever=db.as_retriever())

    query = "What did the president say about Ketanji Brown Jackson"
    answer = qa_with_docs.run(query)
    # print(qa_with_docs.memory)

    flow_qa = GenericLCChain(
        name="Wrapper around QA chain",
        description="Answer QA from documents",
        lc_chain=qa_with_docs
    )
    #
    task_message = flow_qa.package_task_message(
        recipient_flow=flow_qa,
        task_name="",
        task_data={"query": query},
        expected_outputs=["answer"]
    )

    ans = flow_qa(task_message)

    print(ans.data)
