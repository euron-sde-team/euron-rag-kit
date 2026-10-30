/** Copy-paste examples for calling a project from code, the shell and CI. */

export type SnippetInput = {
  apiUrl: string;
  project: string;
  collection: string;
  dataset: string;
  key: string;
};

export type Snippets = { python: string; curl: string; cli: string };

export function snippets({ apiUrl, project, collection, dataset, key }: SnippetInput): Snippets {
  const python = [
    "from ragkit import RAGKit",
    "",
    `rk = RAGKit(base_url="${apiUrl}", api_key="${key}", project="${project}")`,
    `docs = rk.collection("${collection}")`,
    "",
    'result = docs.answer("How do I verify webhook signatures?")',
    "print(result.answer)",
    "for citation in result.citations:",
    "    print(citation.n, citation.document_title, citation.location)",
  ].join("\n");
  const curl = [
    `curl -s ${apiUrl}/api/v1/projects/${project}/collections/${collection}/query \\`,
    `  -H "authorization: Bearer ${key}" \\`,
    '  -H "content-type: application/json" \\',
    `  -d '{"query": "How do I verify webhook signatures?", "top_k": 5}'`,
  ].join("\n");
  const cli = [
    `export RAGKIT_URL=${apiUrl} RAGKIT_PROJECT=${project} RAGKIT_API_KEY=${key}`,
    `ragkit query ${collection} "how do I verify webhook signatures"`,
    `ragkit eval gate ${dataset} --min hit_rate=0.85 --max-drop 0.03`,
  ].join("\n");
  return { python, curl, cli };
}
