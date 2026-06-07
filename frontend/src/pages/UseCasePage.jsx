import { Navigate, useParams } from "react-router-dom";
import { ArticleLayout } from "@/components/blog/ArticleLayout";
import { USE_CASES } from "@/content/registry";

export default function UseCasePage() {
  const { slug } = useParams();
  const post = USE_CASES.find((u) => u.slug === slug);
  if (!post) return <Navigate to="/" replace />;

  return (
    <ArticleLayout post={post} kind="use-cases">
      <p>{post.description}</p>
      <p>
        Here's how InvoiceParsed fits into this workflow — from upload to clean,
        exportable data — and where it saves the most time.
      </p>
    </ArticleLayout>
  );
}
