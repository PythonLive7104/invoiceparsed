import { Navigate, useParams } from "react-router-dom";
import { ArticleLayout } from "@/components/blog/ArticleLayout";
import { BLOG_POSTS } from "@/content/registry";

export default function BlogPost() {
  const { slug } = useParams();
  const post = BLOG_POSTS.find((p) => p.slug === slug);
  if (!post) return <Navigate to="/blog" replace />;

  return (
    <ArticleLayout post={post} kind="blog">
      <p>
        {post.description} This guide walks through the fastest, most accurate way
        to get there with InvoiceParsed.
      </p>
      <h2 className="text-xl font-semibold text-white">Why automate invoice extraction?</h2>
      <p>
        Manually re-typing invoice fields is slow and error-prone. An AI invoice
        parser reads the document, understands its layout, and returns labelled,
        structured data — vendor, line items, tax and totals — that you can export
        or push straight into your accounting stack.
      </p>
      <h2 className="text-xl font-semibold text-white">How it works</h2>
      <p>
        Upload a PDF or image, and InvoiceParsed returns structured JSON or CSV in
        seconds, with a confidence score on every field so you know what to review.
      </p>
    </ArticleLayout>
  );
}
