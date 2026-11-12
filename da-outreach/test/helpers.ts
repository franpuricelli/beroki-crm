export const MARRONE = {
	da: "A006971478",
	council: "Brisbane City Council",
	project: "Marrone",
	address: "37-39 Browning St, South Brisbane QLD 4101",
	units: 97,
	decision: { status: "Approved", date: "2026-11-02" },
	da_url: "https://developmenti.brisbane.qld.gov.au/Home/FilterDirect?filters=DANumber%3DA006971478",
	companies: [
		{ name: "Dalcott", role: "developer", domain: "dalcott.com.au", linkedin: "https://www.linkedin.com/company/dalcott/", confidence: "inferred", why: "same address, 97 units and architect on dalcott.com.au/projects/marrone", source: "https://www.dalcott.com.au/projects/marrone" },
		{ name: "Mewing Planning Consultants", role: "planner", confidence: "inferred", why: "headline de LinkedIn de Second Planner" },
	],
	people: [
		{ first_name: "Sample", last_name: "Person", company: "Dalcott", title: "Managing Director", role_on_deal: "Developer – decision maker", linkedin: "https://www.linkedin.com/in/sample-person", email: null, phone: null, kairon_lead_id: "lead_sample0000000000000000001", confidence: "confirmed", source: "https://www.dalcott.com.au/about" },
		{ first_name: "Second", last_name: "Planner", company: "Mewing Planning Consultants", title: "Associate Director", role_on_deal: "Planner", linkedin: "https://www.linkedin.com/in/second-planner", kairon_lead_id: "lead_sample0000000000000000002", confidence: "inferred", why: "rol en el DA inferido por su cargo" },
	],
	whos_who: "Dalcott desarrolla; Mewing es el planner.",
} as const;
