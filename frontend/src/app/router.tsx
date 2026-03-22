import { createBrowserRouter, RouterProvider, Link, Outlet } from "react-router-dom";
import { DashboardPage } from "../pages/dashboard";
import { ScheduleJobPage } from "../pages/schedule-job";
import { JobDetailPage } from "../pages/job-detail/JobDetailPage";

function NavLayout() {
  return (
    <div>
      <nav
        style={{
          background: "#1e40af",
          color: "#fff",
          padding: "0 24px",
          display: "flex",
          alignItems: "center",
          gap: 24,
          height: 52,
        }}
      >
        <span style={{ fontWeight: 700, fontSize: 18 }}>Lightcron</span>
        <Link
          to="/"
          style={{ color: "#bfdbfe", textDecoration: "none", fontSize: 14 }}
        >
          Dashboard
        </Link>
        <Link
          to="/jobs/new"
          style={{ color: "#bfdbfe", textDecoration: "none", fontSize: 14 }}
        >
          Schedule Job
        </Link>
      </nav>
      <main style={{ padding: "32px 24px", maxWidth: 1024, margin: "0 auto" }}>
        <Outlet />
      </main>
    </div>
  );
}

const router = createBrowserRouter([
  {
    element: <NavLayout />,
    children: [
      { path: "/", element: <DashboardPage /> },
      { path: "/jobs/new", element: <ScheduleJobPage /> },
      { path: "/jobs/:job_id", element: <JobDetailPage /> },
    ],
  },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
