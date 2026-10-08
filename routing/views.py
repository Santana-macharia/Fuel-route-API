import json

from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from .services import planner
from .services.errors import RoutingError


def _payload(request):
    if request.method == "GET":
        return request.GET
    if not request.body:
        return {}
    try:
        data = json.loads(request.body)
    except ValueError:
        raise RoutingError("Body must be valid JSON.", 400)
    if not isinstance(data, dict):
        raise RoutingError("Body must be a JSON object.", 400)
    return data


@csrf_exempt
@require_http_methods(["GET", "POST"])
def route_plan(request):
    try:
        data = _payload(request)
        start, finish = data.get("start"), data.get("finish")
        if not (isinstance(start, str) and start.strip() and isinstance(finish, str) and finish.strip()):
            raise RoutingError("Both 'start' and 'finish' are required (address, or 'lat,lng').", 400)
        result = planner.plan_route(start, finish)
    except RoutingError as e:
        return JsonResponse({"error": e.message}, status=e.status)

    result = dict(result)
    result["map_url"] = request.build_absolute_uri(reverse("route-map", args=[result.pop("map_id")]))
    return JsonResponse(result, json_dumps_params={"separators": (",", ":")})


@require_GET
def route_map(request, map_id):
    result = planner.get_cached_route(map_id)
    if result is None:
        raise Http404("Route expired or unknown. Call POST /api/route/ again to regenerate it.")
    return render(request, "routing/map.html", {"data": result})
