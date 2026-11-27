
import type { CourtPrepResponse } from "./courtPrep";

const daysFromNow = (days: number, hour = 10): string => {
  const d = new Date(Date.now() + days * 86_400_000);
  d.setUTCHours(hour, 15, 0, 0);
  return d.toISOString().replace(/\.\d+Z$/, "Z");
};
const day = (days: number): string => daysFromNow(days).slice(0, 10);

export function stubCourtPrep(): CourtPrepResponse {
  return {
    in_review: 2,
    items: [
      { matter_id: "9001", client_name: "Stub Testperson", hearing_id: 1, hearing_date: day(2), hearing_time: "10:00", hearing_type: "FHDRA", court: "Stub Family Court", is_final: false, milestones: { court_informed: daysFromNow(-12), client_informed: daysFromNow(-10), papers_sent: daysFromNow(-9), opponent_served: daysFromNow(-7), counsel_booked: daysFromNow(-6), bundle_sent: daysFromNow(-1), brief_sent: daysFromNow(-1) } },
      { matter_id: "9002", client_name: "Second Stubperson", hearing_id: 2, hearing_date: day(5), hearing_time: "14:30", hearing_type: "Directions", court: "Stub Family Court", is_final: false, milestones: { court_informed: daysFromNow(-8), client_informed: daysFromNow(-7), papers_sent: daysFromNow(-6), opponent_served: "", counsel_booked: "yes", bundle_sent: "", brief_sent: "" } },
      { matter_id: "9003", client_name: "Third Stubperson", hearing_id: 3, hearing_date: day(9), hearing_time: "10:00", hearing_type: "Final hearing", court: "Other Stub Court", is_final: true, milestones: { court_informed: daysFromNow(-5), client_informed: "", papers_sent: "", opponent_served: "", counsel_booked: "", bundle_sent: "", brief_sent: "" } },
      { matter_id: "9001", client_name: "Stub Testperson", hearing_id: 5, hearing_date: day(12), hearing_time: "11:00", hearing_type: "Review", court: "Stub Family Court", is_final: false, milestones: { court_informed: "", client_informed: "", papers_sent: "", opponent_served: "", counsel_booked: "", bundle_sent: "", brief_sent: "" } },
      { matter_id: "9004", client_name: "Stub Samename", hearing_id: 4, hearing_date: day(14), hearing_time: "", hearing_type: "", court: "", is_final: false, milestones: { court_informed: "", client_informed: "", papers_sent: "", opponent_served: "", counsel_booked: "", bundle_sent: "", brief_sent: "" } },
    ],
  };
}
