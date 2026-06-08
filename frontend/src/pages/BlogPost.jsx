import { Navigate, useParams } from "react-router-dom";
import { ArticleLayout } from "@/components/blog/ArticleLayout";
import { BLOG_POSTS } from "@/content/registry";

export default function BlogPost() {
  const { slug } = useParams();
  const post = BLOG_POSTS.find((p) => p.slug === slug);
  if (!post) return <Navigate to="/blog" replace />;
  return <ArticleLayout post={post} kind="blog" />;
}
