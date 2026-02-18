// "use client";

// import React, { useState } from "react";
// import { Box, Button, TextField, Typography, Alert } from "@mui/material";

// const SupportForm = () => {
//   const [issue, setIssue] = useState("");
//   const [name, setName] = useState("");
//   const [email, setEmail] = useState("");
//   const [subject, setSubject] = useState("");
//   const [submitted, setSubmitted] = useState(false);
//   const [error, setError] = useState("");
//   const [ticketNumber, setTicketNumber] = useState("");

//   const handleSubmit = async (e: React.FormEvent) => {
//     e.preventDefault();
//     setError("");
//     setSubmitted(false);

//     try {
//       const res = await fetch("http://localhost:8000/support/", {
//         method: "POST",
//         headers: {
//           "Content-Type": "application/x-www-form-urlencoded",
//         },
//         body: new URLSearchParams({
//           issue,
//           name,
//           email,
//           subject: subject || "Support Request",
//         }),
//       });

//       if (!res.ok) throw new Error("Failed to submit");

//       const data = await res.json();
//       setSubmitted(true);
//       setTicketNumber(data.ticket_number);
//       setIssue("");
//       setName("");
//       setEmail("");
//       setSubject("");
//     } catch (err) {
//       setError("Could not submit your issue. Please try again.");
//     }
//   };

//   return (
//     <Box
//       component="form"
//       onSubmit={handleSubmit}
//       sx={{ p: 4, maxWidth: 600, mx: "auto" }}
//     >
//       <Typography variant="h5" gutterBottom>
//         Submit a Support Ticket
//       </Typography>

//       {submitted && (
//         <Alert severity="success" sx={{ mb: 2 }}>
//           Thanks! We'll get back to you. Your ticket number is:{" "}
//           <strong>#{ticketNumber}</strong>
//         </Alert>
//       )}
//       {error && (
//         <Alert severity="error" sx={{ mb: 2 }}>
//           {error}
//         </Alert>
//       )}

//       <TextField
//         label="Your Name"
//         variant="outlined"
//         fullWidth
//         value={name}
//         onChange={(e) => setName(e.target.value)}
//         sx={{ mt: 2 }}
//         required
//       />

//       <TextField
//         label="Your Email"
//         variant="outlined"
//         fullWidth
//         type="email"
//         value={email}
//         onChange={(e) => setEmail(e.target.value)}
//         sx={{ mt: 2 }}
//         required
//       />

//       <TextField
//         label="Subject"
//         variant="outlined"
//         fullWidth
//         value={subject}
//         onChange={(e) => setSubject(e.target.value)}
//         sx={{ mt: 2 }}
//         placeholder="Brief description of your issue"
//       />

//       <TextField
//         label="Describe your issue"
//         variant="outlined"
//         fullWidth
//         multiline
//         rows={4}
//         value={issue}
//         onChange={(e) => setIssue(e.target.value)}
//         sx={{ mt: 2 }}
//         required
//       />

//       <Button type="submit" variant="contained" color="primary" sx={{ mt: 2 }}>
//         Submit Ticket
//       </Button>
//     </Box>
//   );
// };

// export default SupportForm;
