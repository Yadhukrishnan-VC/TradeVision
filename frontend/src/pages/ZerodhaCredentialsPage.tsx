/*
TradeVision AI — Zerodha Credentials Input Page.

Provides a user interface for inputting Zerodha API credentials (API Key, Secret,
Access Token) via a web form. Credentials are submitted to the Django backend
API endpoint /api/v1/zerodha/credentials/ and stored encrypted in the database,
overriding .env environment variables for the session.

Features:
  - Form with masked password inputs for API key, secret, and access token
  - Environment selector (sandbox | live)
  - Product selector (MIS, CNC, NRML)
  - Optional request token field
  - Success/error feedback via toast notifications
  - Persists credentials to DB, making them the priority source over .env
*/

import { useState, useEffect } from "react";
import { apiPost } from "@/api/system";
import { useToast } from "@/components/ui/use-toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Card } from "@/components/ui/card";
import { useNavigate } from "react-router-dom";

interface ZerodhaCredentialsFormValues {
  api_key: string;
  api_secret: string;
  access_token: string;
  request_token?: string;
  product?: "MIS" | "CNC" | "NRML";
  environment?: "sandbox" | "live";
}

export default function ZerodhaCredentialsPage() {
  const [form, setForm] = useState<ZerodhaCredentialsFormValues>({
    api_key: "",
    api_secret: "",
    access_token: "",
    product: "MIS",
    environment: "sandbox",
  });
  const [submitting, setSubmitting] = useState(false);
  const { toast } = useToast();
  const navigate = useNavigate();

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ) => {
    const { name, value, type } = e.target;
    setForm({
      ...form,
      [name]: type === "checkbox" ? value : type === "number" ? Number(value) : value,
    });
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);

    try {
      const response = await apiPost("/api/v1/zerodha/credentials/", {
        api_key: form.api_key,
        api_secret: form.api_secret,
        access_token: form.access_token,
        request_token: form.request_token,
        product: form.product,
        environment: form.environment,
      });

      if (response.success) {
        toast({
          title: "Success",
          description: "Zerodha credentials saved to database. They will override .env values.",
        });
        // Reset form
        setForm({
          api_key: "",
          api_secret: "",
          access_token: "",
          product: "MIS",
          environment: "sandbox",
        });
        // Navigate back or to dashboard
        navigate("/");
      } else {
        toast({
          title: "Error",
          description: "Failed to save credentials.",
          variant: "destructive",
        });
      }
    } catch (error: any) {
      console.error("Zerodha credentials submission error:", error);
      toast({
        title: "Error",
        description: error?.message || "Failed to save credentials",
        variant: "destructive",
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card className="w-full max-w-md mx-auto p-8">
      <h2 className="text-xl font-bold text-center mb-6">Zerodha API Credentials</h2>

      <form onSubmit={onSubmit} className="space-y-4">
        <Input
          type="password"
          name="api_key"
          placeholder="Zerodha API Key"
          value={form.api_key}
          onChange={handleChange}
          required
          disabled={submitting}
        />
        <Input
          type="password"
          name="api_secret"
          placeholder="Zerodha API Secret"
          value={form.api_secret}
          onChange={handleChange}
          required
          disabled={submitting}
        />
        <Input
          type="password"
          name="access_token"
          placeholder="Zerodha Access Token"
          value={form.access_token}
          onChange={handleChange}
          required
          disabled={submitting}
        />

        <Select
          name="product"
          value={form.product}
          onValueChange={handleChange}
          disabled={submitting}
        >
          <SelectTrigger>
            <SelectValue placeholder="Select product" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="MIS">MIS - Intraday Square-off</SelectItem>
            <SelectItem value="CNC">CNC - Delivery</SelectItem>
            <SelectItem value="NRML">NRML - Normal</SelectItem>
          </SelectContent>
        </Select>

        <Select
          name="environment"
          value={form.environment}
          onValueChange={handleChange}
          disabled={submitting}
        >
          <SelectTrigger>
            <SelectValue placeholder="Select environment" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="sandbox">Sandbox</SelectItem>
            <SelectItem value="live">Live</SelectItem>
          </SelectContent>
        </Select>

        {form.request_token && (
          <Input
            type="password"
            name="request_token"
            placeholder="Request Token (optional)"
            value={form.request_token || ""}
            onChange={handleChange}
            disabled={submitting}
          />
        )}

        <Button
          type="submit"
          disabled={submitting}
          className="w-full"
        >
          {submitting ? "Saving..." : "Save Zerodha Credentials"}
        </Button>
      </form>
    </Card>
  );
}