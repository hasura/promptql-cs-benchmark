interface IssueCreditsResponse {
  /**
   * Invoice id for credit issue
   */
  stripe_invoice_id?: string,
  /**
   * status of credit issue. one of 'success', 'failed', 'pending'
   */
  status: string

}

/**
 * Issue credits or refund to project owner. 
 */
export async function issueCreditsOrRefund(
  /**
   * email of the project's owner
   */
  email: string,
  owner_id: string,
  project_id: string,
  /**
   * In US dollar, e.g. 10.5 or 100
   */
  amount: number
): Promise<IssueCreditsResponse> {
  const result = {
    "data": {
      "stripe_invoice_id": "stripe_fake_invoice_id_123_987",
      "status": "success"
    } as IssueCreditsResponse,
    "error": null
  }
  if (result.data) {
    return result.data;
  } else {
    throw result.error;
  }
}