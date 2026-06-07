import { Navigate, useParams } from "react-router-dom";
import { ArticleLayout } from "@/components/blog/ArticleLayout";
import { COMPARISONS } from "@/content/registry";

export default function ComparePage() {
  const { slug } = useParams();
  const post = COMPARISONS.find((c) => c.slug === slug);
  if (!post) return <Navigate to="/" replace />;

  return (
    <ArticleLayout post={post} kind="compare">
      <p>{post.description}</p>
      <p>
        Below we break down the practical differences in speed, accuracy, setup and
        cost so you can decide what fits your invoice volume and workflow.
      </p>
    </ArticleLayout>
  );
}
