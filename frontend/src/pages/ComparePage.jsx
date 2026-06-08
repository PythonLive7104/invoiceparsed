import { Navigate, useParams } from "react-router-dom";
import { ArticleLayout } from "@/components/blog/ArticleLayout";
import { COMPARISONS } from "@/content/registry";

export default function ComparePage() {
  const { slug } = useParams();
  const post = COMPARISONS.find((c) => c.slug === slug);
  if (!post) return <Navigate to="/" replace />;
  return <ArticleLayout post={post} kind="compare" />;
}
