import pytest
from directory.models import Firm, Opportunity
from directory.views import _apply_filters

@pytest.mark.django_db
def test_search_words_span_fields_and_preserve_filters():
    firm = Firm.objects.create(name="Goldman Sachs", slug="goldman-search")
    match = Opportunity.objects.create(firm=firm, title="Summer Analyst", location="New York", url="https://example.com/search1", bucket="internship")
    Opportunity.objects.create(firm=firm, title="Summer Analyst", location="London", url="https://example.com/search2", bucket="internship")
    selection = dict(q="  NEW   analyst Goldman york ", region="", provider="", firm=[], year="", role="", track="")
    assert list(_apply_filters(Opportunity.objects.all(), selection)) == [match]
    selection["q"] = "Goldman missing"
    assert not _apply_filters(Opportunity.objects.all(), selection).exists()
    selection["q"] = ""
    assert _apply_filters(Opportunity.objects.all(), selection).count() == 2
